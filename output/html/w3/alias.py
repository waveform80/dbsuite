# $Header$
# vim: set noet sw=4 ts=4:

from db.alias import Alias
from output.html.w3.document import W3MainDocument

class W3AliasDocument(W3MainDocument):
	def __init__(self, site, alias):
		assert isinstance(alias, Alias)
		super(W3AliasDocument, self).__init__(site, alias)

	def create_sections(self):
		fields = [obj for (name, obj) in sorted(self.dbobject.fields.items(), key=lambda (name, obj): name)]
		dependents = [obj for (name, obj) in sorted(self.dbobject.dependents.items(), key=lambda (name, obj): name)]
		self.section('description', 'Description')
		self.add(self.p(self.format_description(self.dbobject.description)))
		self.section('attributes', 'Attributes')
		self.add(self.table(
			head=[(
				'Attribute',
				'Value',
				'Attribute',
				'Value'
			)],
			data=[
				(
					self.a(self.site.documents['created.html']),
					self.dbobject.created,
					self.a(self.site.documents['createdby.html']),
					self.dbobject.definer,
				),
				(
					'Alias For',
					{'colspan': '3', '': self.a_to(self.dbobject.relation, qualifiedname=True)},
				),
			]
		))
		if len(fields) > 0:
			self.section('field_desc', 'Field Descriptions')
			self.add(self.table(
				head=[(
					"Name",
					"Description"
				)],
				data=[(
					field.name,
					self.format_description(field.description, firstline=True)
				) for field in fields]
			))
			self.section('field_schema', 'Field Schema')
			self.add(self.table(
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
					field.name,
					field.datatype_str,
					field.nullable,
					field.key_index,
					field.cardinality
				) for field in fields]
			))
		if len(dependents) > 0:
			self.section('dependents', 'Dependent Relations')
			self.add(self.table(
				head=[(
					"Name",
					"Type",
					"Description"
				)],
				data=[(
					self.a_to(dep, qualifiedname=True),
					dep.type_name,
					self.format_description(dep.description, firstline=True)
				) for dep in dependents]
			))
		self.section('diagram', 'Diagram')
		self.add(self.img_of(self.dbobject))
		self.section('sql', 'SQL Definition')
		self.add(self.pre(self.format_sql(self.dbobject.create_sql), attrs={'class': 'sql'}))

class W3AliasGraph(W3GraphDocument):
	def __init__(self, site, alias):
		assert isinstance(alias, Alias)
		super(W3AliasGraph, self).__init__(site, alias)
	
	def create_graph(self):
		alias = self.dbobject
		alias_node = self.add_dbobject(alias, selected=True)
		target_node = self.add_dbobject(alias.relation)
		for dependent in alias.dependent_list:
			dep_node = self.add_dbobject(dependent)
			dep_edge = dep_node.connect_to(alias_node)
			dep_edge.label = '<uses>'
		target_edge = alias_node.connect_to(target_node)
		target_edge.label = '<for>'

