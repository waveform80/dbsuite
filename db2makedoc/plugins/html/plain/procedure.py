# vim: set noet sw=4 ts=4:

from db2makedoc.db import Procedure
from db2makedoc.plugins.html.plain.document import PlainMainDocument, tag

access = {
	None: 'No SQL',
	'N':  'No SQL',
	'C':  'Contains SQL',
	'R':  'Read-only SQL',
	'M':  'Modifies SQL',
}

class PlainProcedureDocument(PlainMainDocument):
	def __init__(self, site, procedure):
		assert isinstance(procedure, Procedure)
		super(PlainProcedureDocument, self).__init__(site, procedure)
	
	def generate_sections(self):
		result = super(PlainProcedureDocument, self).generate_sections()
		overloads = self.dbobject.schema.procedures[self.dbobject.name]
		result.append((
			'description', 'Description', [
				tag.p(self.format_prototype(self.dbobject.prototype)),
				tag.p(self.format_comment(self.dbobject.description)),
				# XXX What about the IN/OUT/INOUT state of procedure parameters?
				tag.dl((
					(tag.dt(param.name), tag.dd(self.format_comment(param.description)))
					for param in self.dbobject.param_list
				))
			]
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
						tag.td(self.site.url_document('sqlaccess.html').link()),
						tag.td(access[self.dbobject.sql_access]),
						tag.td(self.site.url_document('nullcall.html').link()),
						tag.td(self.dbobject.null_call)
					),
					tag.tr(
						tag.td(self.site.url_document('externalaction.html').link()),
						tag.td(self.dbobject.external_action),
						tag.td(self.site.url_document('deterministic.html').link()),
						tag.td(self.dbobject.deterministic)
					),
					tag.tr(
						tag.td(self.site.url_document('specificname.html').link()),
						tag.td(self.dbobject.specific_name, colspan=3)
					)
				)
			)
		))
		if len(overloads) > 1:
			result.append((
				'overloads', 'Overloaded Versions',
				tag.table(
					tag.thead(
						tag.tr(
							tag.th('Prototype'),
							tag.th('Specific Name')
						)
					),
					tag.tbody((
						tag.tr(
							tag.td(self.format_prototype(overload.prototype)),
							tag.td(tag.a(overload.specific_name, href=self.site.object_document(overload).url))
						) for overload in overloads if overload != self.dbobject
					))
				)
			))
		if self.dbobject.create_sql:
			result.append((
				'sql', 'SQL Definition',
				tag.pre(self.format_sql(self.dbobject.create_sql), class_='sql')
			))
		return result
