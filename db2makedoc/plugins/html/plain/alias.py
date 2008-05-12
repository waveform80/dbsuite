# vim: set noet sw=4 ts=4:

from db2makedoc.db import Alias
from db2makedoc.plugins.html.plain.document import PlainMainDocument, PlainGraphDocument, tag

def _inc_index(i):
	if i is None:
		return i
	else:
		return i + 1

class PlainAliasDocument(PlainMainDocument):
	def __init__(self, site, alias):
		assert isinstance(alias, Alias)
		super(PlainAliasDocument, self).__init__(site, alias)

	def generate_sections(self):
		result = super(PlainAliasDocument, self).generate_sections()
		fields = [obj for (name, obj) in sorted(self.dbobject.fields.iteritems(), key=lambda (name, obj): name)]
		dependents = [obj for (name, obj) in sorted(self.dbobject.dependents.iteritems(), key=lambda (name, obj): name)]
		result.append((
			'description', 'Description',
			tag.p(self.format_comment(self.dbobject.description))
		))
		result.append((
			'attributes', 'Attributes',
			tag.table(
				tag.thead(
					tag.tr(
						tag.th('Attribute'),
						tag.th('Value'),
						tag.th('Attribute'),
						tag.th('Value')
					)
				),
				tag.tbody(
					tag.tr(
						tag.td(self.site.url_document('created.html').link()),
						tag.td(self.dbobject.created),
						tag.td(self.site.url_document('createdby.html').link()),
						tag.td(self.dbobject.owner)
					),
					tag.tr(
						tag.td('Alias For'),
						tag.td(self.site.link_to(self.dbobject.relation, qualifiedname=True), colspan=3)
					)
				)
			)
		))
		if len(fields) > 0:
			result.append((
				'fields', 'Fields',
				tag.table(
					tag.thead(
						tag.tr(
							tag.th('#'),
							tag.th('Name'),
							tag.th('Type'),
							tag.th('Nulls'),
							tag.th('Key Pos'),
							tag.th('Cardinality'),
							tag.th('Description')
						)
					),
					tag.tbody((
						tag.tr(
							tag.td(field.position + 1),
							tag.td(field.name),
							tag.td(field.datatype_str),
							tag.td(field.nullable),
							tag.td(_inc_index(field.key_index)), # XXX For Py2.5: field.key_index + 1 if field.key_index is not None else None,
							tag.td(field.cardinality),
							tag.td(self.format_comment(field.description, summary=True))
						) for field in fields
					))
				)
			))
		if len(dependents) > 0:
			result.append((
				'dependents', 'Dependent Relations',
				tag.table(
					tag.thead(
						tag.tr(
							tag.th('Name'),
							tag.th('Type'),
							tag.th('Description')
						)
					),
					tag.tbody((
						tag.tr(
							tag.td(self.site.link_to(dep, qualifiedname=True)),
							tag.td(dep.type_name),
							tag.td(self.format_comment(dep.description, summary=True))
						) for dep in dependents
					))
				)
			))
		result.append((
			'diagram', 'Diagram',
			self.site.img_of(self.dbobject)
		))
		result.append((
			'sql', 'SQL Definition',
			tag.pre(self.format_sql(self.dbobject.create_sql), class_='sql')
		))
		return result

class PlainAliasGraph(PlainGraphDocument):
	def __init__(self, site, alias):
		assert isinstance(alias, Alias)
		super(PlainAliasGraph, self).__init__(site, alias)
	
	def generate(self):
		super(PlainAliasGraph, self).generate()
		alias = self.dbobject
		alias_node = self.add(alias, selected=True)
		target_node = self.add(alias.relation)
		target_edge = alias_node.connect_to(target_node)
		target_edge.label = '<for>'
		target_edge.arrowhead = 'onormal'
		for dependent in alias.dependent_list:
			dep_node = self.add(dependent)
			dep_edge = dep_node.connect_to(alias_node)
			dep_edge.label = '<uses>'
			dep_edge.arrowhead = 'onormal'
		return self.graph
