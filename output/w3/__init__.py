#!/usr/bin/env python
# $Header$
# vim: set noet sw=4 ts=4:

import sys
import os.path
import datetime
import logging
import re
from decimal import Decimal
from output.w3.htmlutils import *
from output.w3.document import Document
from db.database import DocDatabase
from db.table import DocTable
from db.view import DocView
from db.check import DocCheck
from db.foreignkey import DocForeignKey
from db.uniquekey import DocUniqueKey, DocPrimaryKey
from db.function import DocFunction
from xml.sax.saxutils import quoteattr, escape
from sql.tokenizer import DB2UDBSQLTokenizer
from sql.formatter import SQLFormatter
from sql.htmlhighlighter import SQLHTMLHighlighter

__all__ = ['DocOutput']

def filename(object):
	"""Returns a unique, but deterministic filename for the specified object"""
	return "%s.html" % (object.identifier)

def linkTo(object, attrs={}, qualifiedName=False):
	"""Generates an XHTML link to an object"""
	a = {'href': filename(object)}
	a.update(attrs)
	if qualifiedName:
		return makeTag('a', a, escape(object.qualifiedName))
	else:
		return makeTag('a', a, escape(object.name))

def popupLink(target, content, width=400, height=300):
	return makeTag('a', {'href': 'javascript:popup("%s","internal",%d,%d)' % (target, height, width)}, content)

class DocOutput(object):
	"""HTML documentation writer class -- IBM w3 Intranet v8 standard"""

	def __init__(self, database, path="."):
		"""Initializes an instance of the class.

		DocOutput is a "one-shot" class in that initializing and instance also
		causes the documentation to be written by the instance (which is then
		usually discarded).
		"""
		super(DocOutput, self).__init__()
		self._updated = datetime.date.today()
		self._database = database
		self._path = path
		self._tokenizer = DB2UDBSQLTokenizer()
		self._formatter = SQLFormatter()
		self._highlighter = SQLHTMLHighlighter()
		# Write the documentation files
		self.writeDatabase(database)
		for schema in database.schemas.itervalues():
			self.writeSchema(schema)
			for relation in schema.relations.itervalues():
				self.writeRelation(relation)
				if isinstance(relation, DocTable):
					for constraint in relation.constraints.itervalues():
						self.writeConstraint(constraint)
			for index in schema.indexes.itervalues():
				self.writeIndex(index)
			for function in schema.functions.itervalues():
				self.writeFunction(function)
		for tablespace in database.tablespaces.itervalues():
			self.writeTablespace(tablespace)

	def formatSql(self, sql):
		# Tokenize, reformat, and then syntax highlight the provided code
		tokens = self._tokenizer.parse(sql)
		tokens = self._formatter.parse(tokens)
		html = self._highlighter.parse(tokens)
		return html
		#return self._highlighter.parse(self._formatter.parse(self._tokenizer.parse(sql)))
	
	findref = re.compile(r"@([A-Za-z_$#@][A-Za-z0-9_$#@]*(\.[A-Za-z_$#@][A-Za-z0-9_$#@]*){0,2})\b")
	findfmt = re.compile(r"\B([/_*])(\w+)\1\B")
	def formatDescription(self, text):
		"""Converts simple prefix-based markup in text into HTML.
		
		References in the provided text (specified as @-prefix qualified names)
		are returned as links to the targetted objects (the objects are located
		with the find() method of the DocDatabase object at the root of the
		object hierarchy).
		
		Highlights in the text are also converted. Currently *bold* text is
		converted to <strong> tags, /italic/ text is converted to <em> tags,
		and _underlined_ text is convert to <u> tags.
		
		The resulting string is valid HTML; that is, all characters which
		require converting to character entities are converted using the
		escape() function of the xml.sax.saxutils unit.
		"""
		# Replace refs and fmt modifiers with HTML
		start = 0
		result = ''
		while True:
			matchref = self.findref.search(text, start)
			matchfmt = self.findfmt.search(text, start)
			if matchref is not None and (matchfmt is None or matchfmt.start(0) > matchref.start(0)):
				result += escape(text[start:matchref.start(0)])
				start = matchref.end(0)
				target = self._database.find(matchref.group(1))
				if target is None:
					result += escape(matchref.group(1))
				else:
					result += linkTo(target, qualifiedName=True)
			elif matchfmt is not None and (matchref is None or matchfmt.start(0) < matchref.start(0)):
				result += escape(text[start:matchfmt.start(0)])
				start = matchfmt.end(0)
				if matchfmt.group(1) == '*':
					result += makeTag('strong', {}, matchfmt.group(2))
				elif matchfmt.group(1) == '/':
					result += makeTag('em', {}, matchfmt.group(2))
				elif matchfmt.group(1) == '_':
					result += makeTag('u', {}, matchfmt.group(2))
			else:
				result += text[start:]
				break
		# Replace line breaks with line break tags
		return result.replace('\n', '<br />')

	def createMenu(self, item, active=True):
		result = []
		while True:
			result = [(filename(item), item.name, result, active)]
			active = False
			item = item.parent
			if item is None:
				break
		result.insert(0, ('index.html', 'Home', [], False))
		return result

	def createMenuLevel(self, items, index):
		if len(items) <= 10:
			slice = items
		elif index <= 3:
			slice = items[:7]
		elif index >= len(items) - 3:
			slice = items[-7:]
		else:
			slice = items[index - 3:index + 3]
		return [(filename(item), item.name, []) for item in slice]

	def newDocument(self, object):
		"""Creates a new Document object for the specified object.
		
		This method returns a new Document object with most of the attributes
		(like doctitle, sitetitle, etc.) filled in from the specified object.
		"""
		doc = Document()
		# Use a single value for the update date of all documents produced by the class
		doc.updated = self._updated
		doc.author = ''
		doc.authoremail = ''
		doc.title = "%s %s" % (object.typeName, object.qualifiedName)
		doc.sitetitle = "%s Documentation" % (self._database.name)
		doc.keywords = [self._database.name, object.typeName, object.name, object.qualifiedName]
		o = object
		while not o is None:
			doc.breadcrumbs.insert(0, (filename(o), '%s %s' % (o.typeName, o.name)))
			o = o.parent
		doc.breadcrumbs.insert(0, ('index.html', 'Home'))
		# XXX Construct the menu properly
		doc.menu = self.createMenu(object)
		#doc.menu = [('index.html', 'Home', []), (filename(self._database), 'Documentation', [])]
		return doc

	def writeDatabase(self, database):
		logging.debug("Writing documentation for database to %s" % (filename(database)))
		schemas = [obj for (name, obj) in sorted(database.schemas.items(), key=lambda (name, obj):name)]
		tbspaces = [obj for (name, obj) in sorted(database.tablespaces.items(), key=lambda (name, obj):name)]
		doc = self.newDocument(database)
		if len(schemas) > 0:
			doc.addSection(id='schemas', title='Schemas')
			doc.addPara("""The following table contains all schemas (logical
				object containers) in the database. Click on a schema name to
				view the documentation for that schema, including a list of all
				objects that exist within it.""")
			doc.addContent(makeTable(
				head=[(
					"Name",
					"Description"
				)],
				data=[(
					linkTo(schema),
					self.formatDescription(schema.description)
				) for schema in schemas]
			))
		if len(tbspaces) > 0:
			doc.addSection(id='tbspaces', title='Tablespaces')
			doc.addPara("""The following table contains all tablespaces
				(physical object containers) in the database. Click on a
				tablespace name to view the documentation for that tablespace,
				including a list of all tables and/or indexes that exist within
				it.""")
			doc.addContent(makeTable(
				head=[(
					"Name",
					"Description"
				)],
				data=[(
					linkTo(tbspace),
					self.formatDescription(tbspace.description)
				) for tbspace in tbspaces]
			))
		doc.write(os.path.join(self._path, filename(database)))

	def writeSchema(self, schema):
		logging.debug("Writing documentation for schema %s to %s" % (schema.name, filename(schema)))
		relations = [obj for (name, obj) in sorted(schema.relations.items(), key=lambda (name, obj): name)]
		routines = [obj for (name, obj) in sorted(schema.specificRoutines.items(), key=lambda (name, obj): name)]
		indexes = [obj for (name, obj) in sorted(schema.indexes.items(), key=lambda (name, obj): name)]
		doc = self.newDocument(schema)
		if len(relations) > 0:
			doc.addSection(id='relations', title='Relations')
			doc.addPara("""The following table contains all the relations
				(tables and views) that the schema contains. Click on a
				relation name to view the documentation for that relation,
				including a list of all objects that exist within it, and that
				the relation references.""")
			doc.addContent(makeTable(
				head=[(
					"Name",
					"Type",
					"Description"
				)],
				data=[(
					linkTo(relation),
					escape(relation.typeName),
					self.formatDescription(relation.description)
				) for relation in relations]
			))
		if len(routines) > 0:
			doc.addSection(id='routines', title='Routines')
			doc.addPara("""The following table contains all the routines
				(functions, stored procedures, and methods) that the schema
				contains. Click on a routine name to view the documentation for
				that routine.""")
			doc.addContent(makeTable(
				head=[(
					"Name",
					"Type",
					"Description"
				)],
				data=[(
					linkTo(routine),
					escape(routine.typeName),
					self.formatDescription(routine.description)
				) for routine in routines]
			))
		if len(indexes) > 0:
			doc.addSection(id='indexes', title='Indexes')
			doc.addPara("""The following table contains all the indexes that
				the schema contains. Click on an index name to view the
				documentation for that index.""")
			doc.addContent(makeTable(
				head=[(
					"Name",
					"Applies To",
					"Description")],
				data=[(
					linkTo(index),
					linkTo(index.table, qualifiedName=True),
					self.formatDescription(index.description)
				) for index in indexes]
			))
		doc.write(os.path.join(self._path, filename(schema)))

	def writeTablespace(self, tbspace):
		logging.debug("Writing documentation for tablespace %s to %s" % (tbspace.name, filename(tbspace)))
		tables = [obj for (name, obj) in sorted(tbspace.tables.items(), key=lambda (name, obj): name)]
		indexes = [obj for (name, obj) in sorted(tbspace.indexes.items(), key=lambda (name, obj): name)]
		doc = self.newDocument(tbspace)
		doc.addSection(id='attributes', title='Attributes')
		doc.addPara("""The following table notes various "vital statistics"
			of the tablespace.""")
		doc.addContent(makeTable(
			head=[(
				"Attribute",
				"Value",
				"Attribute",
				"Value"
			)],
			data=[
				(
					popupLink("created.html", "Created"),
					tbspace.created,
					popupLink("tables.html", "# Tables"),
					len(tables),
				),
				(
					popupLink("createdby.html", "Created By"),
					escape(tbspace.definer),
					popupLink("cardinality.html", "# Indexes"),
					len(indexes),
				),
				(
					popupLink("managedby.html", "Managed By"),
					escape(tbspace.managedBy),
					popupLink("tbspacetype.html", "Data Type"),
					escape(tbspace.dataType),
				),
				(
					popupLink("extentsize.html", "Extent Size"),
					tbspace.extentSize,
					popupLink("prefetchsize.html", "Prefetch Size"),
					tbspace.prefetchSize,
				),
				(
					popupLink("pagesize.html", "Page Size"),
					tbspace.pageSize,
					popupLink("droprecovery.html", "Drop Recovery"),
					tbspace.dropRecovery,
				),
			]))
		if len(tables) > 0:
			doc.addSection(id='tables', title='Tables')
			doc.addPara("""The following table contains all the tables that
				the tablespace contains. Click on a table name to view the
				documentation for that table.""")
			doc.addContent(makeTable(
				head=[(
					"Name",
					"Description"
				)],
				data=[(
					linkTo(table, qualifiedName=True),
					self.formatDescription(table.description)
				) for table in tables]
			))
		if len(indexes) > 0:
			doc.addSection(id='indexes', title='Indexes')
			doc.addPara("""The following table contains all the indexes that
				the tablespace contains. Click on an index name to view the
				documentation for that index.""")
			doc.addContent(makeTable(
				head=[(
					"Name",
					"Applies To",
					"Description"
				)],
				data=[(
					linkTo(index, qualifiedName=True),
					linkTo(index.table, qualifiedName=True),
					self.formatDescription(index.description)
				) for index in indexes]
			))
		doc.write(os.path.join(self._path, filename(tbspace)))

	def writeTable(self, table):
		logging.debug("Writing documentation for table %s to %s" % (table.name, filename(table)))
		fields = [obj for (name, obj) in sorted(table.fields.items(), key=lambda (name, obj): name)]
		indexes = [obj for (name, obj) in sorted(table.indexes.items(), key=lambda (name, obj): name)]
		constraints = [obj for (name, obj) in sorted(table.constraints.items(), key=lambda (name, obj): name)]
		dependents = [obj for (name, obj) in sorted(table.dependents.items(), key=lambda (name, obj): name)]
		doc = self.newDocument(table)
		doc.addSection(id='attributes', title='Attributes')
		doc.addPara("""The following table notes various "vital statistics"
			of the table (such as cardinality -- the number of rows in the
			table). Note that many of these attributes are only valid as of
			the last time that statistics were gathered for the table (this
			date is recorded in the table).""")
		if table.primaryKey is None:
			keyCount = 0
		else:
			keyCount = len(table.primaryKey.fields)
		doc.addContent(makeTable(
			head=[(
				"Attribute",
				"Value",
				"Attribute",
				"Value"
			)],
			data=[
				(
					'Data Tablespace',
					linkTo(table.dataTablespace),
					'Index Tablespace',
					linkTo(table.indexTablespace),
				),
				(
					'Long Tablespace',
					linkTo(table.longTablespace),
					popupLink("clustered.html", makeTag('acronym', {'title': 'Multi-Dimensional Clustering'}, 'MDC')),
					table.clustered,
				),
				(
					popupLink("created.html", "Created"),
					table.created,
					popupLink("laststats.html", "Last Statistics"),
					table.statsUpdated,
				),
				(
					popupLink("createdby.html", "Created By"),
					escape(table.definer),
					popupLink("cardinality.html", "Cardinality"),
					table.cardinality,
				),
				(
					popupLink("keycolcount.html", "# Key Columns"),
					keyCount,
					popupLink("colcount.html", "# Columns"),
					len(table.fields),
				),
				(
					popupLink("rowpages.html", "Row Pages"),
					table.rowPages,
					popupLink("totalpages.html", "Total Pages"),
					table.totalPages,
				),
				(
					popupLink("dependentrel.html", "Dependent Relations"),
					len(table.dependentList),
					popupLink("locksize.html", "Lock Size"),
					escape(table.lockSize),
				),
				(
					popupLink("append.html", "Append"),
					table.append,
					popupLink("volatile.html", "Volatile"),
					table.volatile,
				),
			]))
		if len(fields) > 0:
			doc.addSection(id='fields', title='Field Descriptions')
			doc.addPara("""The following table contains the fields of the table
				(in alphabetical order) along with the description of each field.
				For information on the structure and attributes of each field see
				the Field Schema section below.""")
			doc.addContent(makeTable(
				head=[(
					"Name",
					"Description"
				)],
				data=[(
					escape(field.name),
					self.formatDescription(field.description)
				) for field in fields]
			))
			doc.addSection(id='field_schema', title='Field Schema')
			doc.addPara("""The following table contains the attributes of the
				fields of the table (again, fields are in alphabetical order,
				though the # column indicates the 1-based position of the field
				within the table).""")
			doc.addContent(makeTable(
				head=[(
					"#",
					"Name",
					"Type",
					"Nulls",
					"Key Pos",
					"Cardinality"
				)],
				data=[(
					field.position + 1,
					escape(field.name),
					escape(field.datatypeStr),
					field.nullable,
					field.keyIndex,
					field.cardinality
				) for field in fields]
			))
		if len(indexes) > 0:
			doc.addSection('indexes', 'Index Descriptions')
			doc.addPara("""The following table details the indexes defined
				against the table, including which fields each index targets.
				For more information about an individual index (e.g. statistics,
				directionality, etc.) click on the index name.""")
			doc.addContent(makeTable(
				head=[(
					"Name",
					"Unique",
					"Fields",
					"Sort Order",
					"Description"
				)],
				data=[(
					linkTo(index, qualifiedName=True),
					index.unique,
					'<br />'.join([escape(ixfield.name) for (ixfield, ixorder) in index.fieldList]),
					'<br />'.join([escape(ixorder) for (ixfield, ixorder) in index.fieldList]),
					self.formatDescription(index.description)
				) for index in indexes]
			))
		if len(constraints) > 0:
			doc.addSection('constraints', 'Constraints')
			doc.addPara("""The following table details the constraints defined
				against the table, including which fields each constraint
				limits or tests. For more information about an individual
				constraint click on the constraint name.""")
			rows = []
			for constraint in constraints:
				if isinstance(constraint, DocForeignKey):
					expression = '<br />'.join([escape("%s -> %s" % (cfield.name, pfield.name)) for (cfield, pfield) in constraint.fields])
				elif isinstance(constraint, DocPrimaryKey) or isinstance(constraint, DocUniqueKey) or isinstance(constraint, DocCheck):
					expression = '<br />'.join([escape(cfield.name) for cfield in constraint.fields])
				else:
					expression = '&nbsp;'
				rows.append((linkTo(constraint), constraint.typeName, expression, constraint.description))
			doc.addContent(makeTable(
				head=[(
					"Name",
					"Type",
					"Fields",
					"Description"
				)],
				data=rows
			))
		if len(dependents) > 0:
			doc.addSection('dependents', 'Dependent Relations')
			doc.addPara("""The following table lists all relations (views or
				materialized query tables) which reference this table in their
				associated SQL statement.""")
			doc.addContent(makeTable(
			    head=[(
					"Name",
					"Type",
					"Description"
				)],
			    data=[(
					linkTo(dep, qualifiedName=True),
					escape(dep.typeName),
					self.formatDescription(dep.description)
				) for dep in dependents]
			))
		doc.addSection('sql', 'SQL Definition')
		doc.addPara("""The SQL which created the table is given below.
			Note that this is not necessarily the same as the actual statement
			used to create the table (it has been reconstructed from the
			content of the system catalog tables and may differ in a number of
			areas).""")
		doc.addContent(makeTag('pre', {'class': 'sql'}, self.formatSql(table.createSql)))
		doc.write(os.path.join(self._path, filename(table)))

	def writeView(self, view):
		logging.debug("Writing documentation for view %s to %s" % (view.name, filename(view)))
		fields = [obj for (name, obj) in sorted(view.fields.items(), key=lambda (name, obj): name)]
		dependencies = [obj for (name, obj) in sorted(view.dependencies.items(), key=lambda (name, obj): name)]
		dependents = [obj for (name, obj) in sorted(view.dependents.items(), key=lambda (name, obj): name)]
		doc = self.newDocument(view)
		doc.addSection(id='attributes', title='Attributes')
		doc.addPara("""The following table notes various "vital statistics"
			of the view.""")
		doc.addContent(makeTable(
			head=[(
				"Attribute",
				"Value",
				"Attribute",
				"Value"
			)],
			data=[
				(
					popupLink("created.html", "Created"),
					view.created,
					popupLink("createdby.html", "Created By"),
					escape(view.definer),
				),
				(
					popupLink("colcount.html", "# Columns"),
					len(view.fields),
					popupLink("valid.html", "Valid"),
					view.valid,
				),
				(
					popupLink("readonly.html", "Read Only"),
					view.readOnly,
					popupLink("checkoption.html", "Check Option"),
					escape(view.check),
				),
				(
					popupLink("dependentrel.html", "Dependent Relations"),
					len(view.dependentList),
					popupLink("dependenciesrel.html", "Dependencies"),
					len(view.dependencyList),
				)
			]))
		if len(fields) > 0:
			doc.addSection(id='fields', title='Field Descriptions')
			doc.addPara("""The following table contains the fields of the view
				(in alphabetical order) along with the description of each field.
				For information on the structure and attributes of each field see
				the Field Schema section below.""")
			doc.addContent(makeTable(
				head=[(
					"Name",
					"Description"
				)],
				data=[(
					escape(field.name),
					self.formatDescription(field.description)
				) for field in fields]
			))
			doc.addSection(id='field_schema', title='Field Schema')
			doc.addPara("""The following table contains the attributes of the
				fields of the view (again, fields are in alphabetical order,
				though the # column indicates the 1-based position of the field
				within the view).""")
			doc.addContent(makeTable(
				head=[(
					"#",
					"Name",
					"Type",
					"Nulls"
				)],
				data=[(
					field.position + 1,
					escape(field.name),
					escape(field.datatypeStr),
					field.nullable
				) for field in fields]
			))
		if len(dependents) > 0:
			doc.addSection('dependents', 'Dependent Relations')
			doc.addPara("""The following table lists all relations (views or
				materialized query tables) which reference this view in their
				associated SQL statement.""")
			doc.addContent(makeTable(
			    head=[(
					"Name",
					"Type",
					"Description"
				)],
			    data=[(
					linkTo(dep, qualifiedName=True),
					escape(dep.typeName),
					self.formatDescription(dep.description)
				) for dep in dependents]
			))
		if len(dependencies) > 0:
			doc.addSection('dependencies', 'Dependencies')
			doc.addPara("""The following table lists all relations (tables,
				views, materialized query tables, etc.) which this view
				references in it's SQL statement.""")
			doc.addContent(makeTable(
				head=[(
					"Name",
					"Type",
					"Description"
				)],
				data=[(
					linkTo(dep, qualifiedName=True),
					escape(dep.typeName),
					self.formatDescription(dep.description)
				) for dep in dependencies]
			))
		doc.addSection('sql', 'SQL Definition')
		doc.addPara("""The SQL which created the view is given below.
			Note that, in the process of storing the definition of a view, DB2
			removes much of the formatting, hence the formatting in the 
			statement below (which this system attempts to reconstruct) is
			not necessarily the formatting of the original statement.""")
		doc.addContent(makeTag('pre', {'class': 'sql'}, self.formatSql(view.createSql)))
		doc.write(os.path.join(self._path, filename(view)))

	def writeRelation(self, relation):
		if isinstance(relation, DocTable):
			self.writeTable(relation)
		elif isinstance(relation, DocView):
			self.writeView(relation)

	def writeIndex(self, index):
		logging.debug("Writing documentation for index %s to %s" % (index.name, filename(index)))
		position = 0
		fields = []
		for (field, ordering) in index.fieldList:
			fields.append((field, ordering, position))
			position += 1
		fields = sorted(fields, key=lambda(field, ordering, position): field.name)
		doc = self.newDocument(index)
		doc.addSection(id='attributes', title='Attributes')
		doc.addPara("""The following table notes various "vital statistics"
			of the index.""")
		if not index.clusterFactor is None:
			clusterRatio = index.clusterFactor # XXX Convert as necessary
		else:
			clusterRatio = index.clusterRatio
		doc.addContent(makeTable(
			head=[(
				"Attribute",
				"Value",
				"Attribute",
				"Value"
			)],
			data=[
				(
					'Table',
					linkTo(index.table),
					'Tablespace',
					linkTo(index.tablespace),
				),
				(
					popupLink("created.html", "Created"),
					index.created,
					popupLink("laststats.html", "Last Statistics"),
					index.statsUpdated,
				),
				(
					popupLink("createdby.html", "Created By"),
					escape(index.definer),
					popupLink("colcount.html", "# Columns"),
					len(fields),
				),
				(
					popupLink("unique.html", "Unique"),
					index.unique,
					popupLink("reversescans.html", "Reverse Scans"),
					index.reverseScans,
				),
				(
					popupLink("leafpages.html", "Leaf Pages"),
					index.leafPages,
					popupLink("sequentialpages.html", "Sequential Pages"),
					index.sequentialPages,
				),
				(
					popupLink("clusterratio.html", "Cluster Ratio"),
					clusterRatio, # see above
					popupLink("density.html", "Density"),
					index.density,
				),
				(
					popupLink("cardinality.html", "Cardinality"),
					'<br />'.join(
						[formatContent(index.cardinality[0])] + 
						['1..%s: %s' % (keynum + 1, formatContent(card)) for (keynum, card) in enumerate(index.cardinality[1])]
					),
					popupLink("levels.html", "Levels"),
					index.levels,
				),
			]))
		if len(fields) > 0:
			doc.addSection(id='fields', title='Fields')
			doc.addPara("""The following table contains the fields of the index
				(in alphabetical order) along with the position of the field in
				the index, the ordering of the field (Ascending or Descending)
				and the description of the field.""")
			doc.addContent(makeTable(
				head=[(
					"#",
					"Name",
					"Order",
					"Description"
				)],
				data=[(
					position + 1,
					escape(field.name),
					ordering,
					self.formatDescription(field.description)
				) for (field, ordering, position) in fields]
			))
		doc.addSection('sql', 'SQL Definition')
		doc.addPara("""The SQL which created the index is given below.
			Note that this is not necessarily the same as the actual statement
			used to create the index (it has been reconstructed from the
			content of the system catalog tables and may differ in a number of
			areas).""")
		doc.addContent(makeTag('pre', {'class': 'sql'}, self.formatSql(index.createSql)))
		doc.write(os.path.join(self._path, filename(index)))
	
	def writeUniqueKey(self, key):
		logging.debug("Writing documentation for unique key %s to %s" % (key.name, filename(key)))
		position = 0
		fields = []
		for field in key.fields:
			fields.append((field, position))
			position += 1
		fields = sorted(fields, key=lambda(field, position): field.name)
		doc = self.newDocument(key)
		doc.addSection(id='attributes', title='Attributes')
		doc.addPara("""The following table notes various "vital statistics"
			of the unique key.""")
		doc.addContent(makeTable(
			head=[(
				"Attribute",
				"Value",
				"Attribute",
				"Value"
			)],
			data=[
				(
					popupLink("createdby.html", "Created By"),
					escape(key.definer),
					popupLink("colcount.html", "# Columns"),
					len(fields),
				),
			]))
		if len(fields) > 0:
			doc.addSection(id='fields', title='Fields')
			doc.addPara("""The following table contains the fields of the key
				(in alphabetical order) along with the position of the field in
				the key, and the description of the field in the key's table.""")
			doc.addContent(makeTable(
				head=[(
					"#",
					"Field",
					"Description"
				)],
				data=[(
					position + 1,
					escape(field.name),
					self.formatDescription(field.description)
				) for (field, position) in fields]
			))
		doc.addSection('sql', 'SQL Definition')
		doc.addPara("""The SQL which can be used to create the key is given
			below. Note that this is not necessarily the same as the actual
			statement used to create the key (it has been reconstructed from
			the content of the system catalog tables and may differ in a number
			of areas).""")
		doc.addContent(makeTag('pre', {'class': 'sql'}, self.formatSql(key.createSql)))
		doc.write(os.path.join(self._path, filename(key)))

	def writeForeignKey(self, key):
		logging.debug("Writing documentation for foreign key %s to %s" % (key.name, filename(key)))
		position = 0
		fields = []
		for (field1, field2) in key.fields:
			fields.append((field1, field2, position))
			position += 1
		fields = sorted(fields, key=lambda(field1, field2, position): field1.name)
		doc = self.newDocument(key)
		doc.addSection(id='attributes', title='Attributes')
		doc.addPara("""The following table notes various "vital statistics"
			of the foreign key.""")
		doc.addContent(makeTable(
			head=[(
				"Attribute",
				"Value",
				"Attribute",
				"Value"
			)],
			data=[
				(
					'Referenced Table',
					linkTo(key.refTable),
					'Referenced Key',
					linkTo(key.refKey),
				),
				(
					popupLink("created.html", "Created"),
					key.created,
					popupLink("createdby.html", "Created By"),
					escape(key.definer),
				),
				(
					popupLink("enforced.html", "Enforced"),
					key.enforced,
					popupLink("queryoptimize.html", "Query Optimizing"),
					key.queryOptimize,
				),
				(
					popupLink("deleterule.html", "Delete Rule"),
					key.deleteRule,
					popupLink("updaterule.html", "Update Rule"),
					key.updateRule,
				),
			]))
		if len(fields) > 0:
			doc.addSection(id='fields', title='Fields')
			doc.addPara("""The following table contains the fields of the key
				(in alphabetical order) along with the position of the field in
				the key, the field in the parent table that is referenced by
				the key, and the description of the field in the key's table.""")
			doc.addContent(makeTable(
				head=[(
					"#",
					"Field",
					"Parent",
					"Description"
				)],
				data=[(
					position + 1,
					escape(field1.name),
					escape(field2.name),
					self.formatDescription(field1.description)
				) for (field1, field2, position) in fields]
			))
		doc.addSection('sql', 'SQL Definition')
		doc.addPara("""The SQL which can be used to create the key is given
			below. Note that this is not necessarily the same as the actual
			statement used to create the key (it has been reconstructed from
			the content of the system catalog tables and may differ in a number
			of areas).""")
		doc.addContent(makeTag('pre', {'class': 'sql'}, self.formatSql(key.createSql)))
		doc.write(os.path.join(self._path, filename(key)))


	def writeCheck(self, check):
		logging.debug("Writing documentation for check constraint %s to %s" % (check.name, filename(check)))
		fields = sorted(list(check.fields), key=lambda(field): field.name)
		doc = self.newDocument(check)
		doc.addSection(id='attributes', title='Attributes')
		doc.addPara("""The following table notes various "vital statistics"
			of the check.""")
		doc.addContent(makeTable(
			head=[(
				"Attribute",
				"Value",
				"Attribute",
				"Value"
			)],
			data=[
				(
					popupLink("created.html", "Created"),
					check.created,
					popupLink("createdby.html", "Created By"),
					escape(check.definer),
				),
				(
					popupLink("enforced.html", "Enforced"),
					check.enforced,
					popupLink("queryoptimize.html", "Query Optimizing"),
					check.queryOptimize,
				),
			]))
		if len(fields) > 0:
			doc.addSection(id='fields', title='Fields')
			doc.addPara("""The following table contains the fields that the
				check references in it's SQL expression, and the description of
				the field in the check's table.""")
			doc.addContent(makeTable(
				head=[(
					"Field",
					"Description"
				)],
				data=[(
					escape(field.name),
					self.formatDescription(field.description)
				) for field in fields]
			))
		doc.addSection('sql', 'SQL Definition')
		doc.addPara("""The SQL which can be used to create the check is given
			below. Note that this is not necessarily the same as the actual
			statement used to create the check (it has been reconstructed from
			the content of the system catalog tables and may differ in a number
			of areas).""")
		doc.addContent(makeTag('pre', {'class': 'sql'}, self.formatSql(check.createSql)))
		doc.write(os.path.join(self._path, filename(check)))

	def writeConstraint(self, constraint):
		if isinstance(constraint, DocUniqueKey):
			self.writeUniqueKey(constraint)
		elif isinstance(constraint, DocForeignKey):
			self.writeForeignKey(constraint)
		elif isinstance(constraint, DocCheck):
			self.writeCheck(constraint)
	
	def writeFunction(self, functions):
		# Note that this method (unlike other methods) is passed a *list* of
		# functions (because functions can be overloaded)
		for function in functions:
			logging.debug("Writing documentation for function %s to %s" % (function.name, filename(function)))
			doc = self.newDocument(function)
			doc.addSection(id='attributes', title='Attributes')
			doc.addPara("""The following table notes the various attributes and
				properties of the function.""")
			doc.addContent(makeTable(
				head=[(
					"Attribute",
					"Value",
					"Attribute",
					"Value"
				)],
				data=[
					(
						popupLink("created.html", "Created"),
						function.created,
						popupLink("funcorigin.html", "Origin"),
						function.origin,
					),
					(
						popupLink("createdby.html", "Created By"),
						escape(function.definer),
						popupLink("funclanguage.html", "Language"),
						function.language,
					),
					(
						popupLink("functype.html", "Type"),
						function.type,
						popupLink("sqlaccess.html", "SQL Access"),
						function.sqlAccess,
					),
					(
						popupLink("castfunc.html", "Cast Function"),
						function.castFunction,
						popupLink("assignfunc.html", "Assign Function"),
						function.assignFunction,
					),
					(
						popupLink("externalaction.html", "External Action"),
						function.externalAction,
						popupLink("deterministic.html", "Deterministic"),
						function.deterministic,
					),
					(
						popupLink("nullcall.html", "Call on NULL"),
						function.nullCall,
						popupLink("fenced.html", "Fenced"),
						function.fenced,
					),
					(
						popupLink("parallelcall.html", "Parallel"),
						function.parallel,
						popupLink("threadsafe.html", "Thread Safe"),
						function.threadSafe,
					),
				]))
			##doc.addSection('sql', 'SQL Definition')
			##doc.addPara("""The SQL which can be used to create the function is given
			##	below. Note that this is not necessarily the same as the actual
			##	statement used to create the function (it has been reconstructed from
			##	the content of the system catalog tables and may differ in a number
			##	of areas).""")
			##doc.addContent(makeTag('pre', {'class': 'sql'}, self.formatSql(function.createSql)))
			doc.write(os.path.join(self._path, filename(function)))

def main():
	pass

if __name__ == "__main__":
	main()