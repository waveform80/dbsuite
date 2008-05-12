# vim: set noet sw=4 ts=4:

from db2makedoc.db import Tablespace
from db2makedoc.plugins.html.plain.document import PlainMainDocument, tag

class PlainTablespaceDocument(PlainMainDocument):
	def __init__(self, site, tablespace):
		assert isinstance(tablespace, Tablespace)
		super(PlainTablespaceDocument, self).__init__(site, tablespace)

	def generate_sections(self):
		result = super(PlainTablespaceDocument, self).generate_sections()
		tables = [obj for (name, obj) in sorted(self.dbobject.tables.items(), key=lambda (name, obj): name)]
		indexes = [obj for (name, obj) in sorted(self.dbobject.indexes.items(), key=lambda (name, obj): name)]
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
						tag.td(self.site.url_document('tables.html').link()),
						tag.td(len(tables))
					),
					tag.tr(
						tag.td(self.site.url_document('createdby.html').link()),
						tag.td(self.dbobject.owner),
						tag.td(self.site.url_document('indexes.html').link()),
						tag.td(len(indexes))
					),
					tag.tr(
						tag.td(self.site.url_document('tbspacetype.html').link()),
						tag.td(self.dbobject.type, colspan=3)
					)
				)
			)
		))
		if len(tables) > 0:
			result.append((
				'tables', 'Tables',
				tag.table(
					tag.thead(
						tag.tr(
							tag.th('Name'),
							tag.th('Description')
						)
					),
					tag.tbody((
						tag.tr(
							tag.td(self.site.link_to(table, qualifiedname=True)),
							tag.td(self.format_comment(table.description, summary=True))
						) for table in tables
					))
				)
			))
		if len(indexes) > 0:
			result.append((
				'indexes', 'Indexes',
				tag.table(
					tag.thead(
						tag.tr(
							tag.th('Name'),
							tag.th('Applies To'),
							tag.th('Description')
						)
					),
					tag.tbody((
						tag.tr(
							tag.td(self.site.link_to(index, qualifiedname=True)),
							tag.td(self.site.link_to(index.table, qualifiedname=True)),
							tag.td(self.format_comment(index.description, summary=True))
						) for index in indexes
					))
				)
			))
		return result
