#!/bin/env python
# $Header$
# vim: set noet sw=4 ts=4:

import db.alias
import output.html.w3

class W3AliasDocument(output.html.w3.W3Document):
	def __init__(self, dbobject, htmlver=XHTML10, htmlstyle=STRICT):
		assert isinstance(self.dbobject, db.alias.Alias)
		super(W3AliasDocument, self).__init__(dbobject, htmlver, htmlstyle)

	def create_sections(self):
		self.section('description', 'Description')
		self.add(self.p(self.format_description(self.dbobject.description)))
		self.section('attributes', 'Attributes')
		self.add(self.p("""The following table notes various "vital statistics" of the alias."""))
		self.add(self.table(
			head=[(
				'Attribute',
				'Value',
				'Attribute',
				'Value'
			)]
			data=[
				(
					self.a('created.html', 'Created', popup=True),
					self.dbobject.created,
					self.a('createdby.html', 'Created By', popup=True),
					self.dbobject.definer,
				),
				(
					'Alias For',
					{'colspan': 3, '': self.a_to(self.dbobject.relation, qualifiedname=True)},
				),
			]
		))
		self.section('sql', 'SQL Definition')
		self.add(self.p("""The SQL which created the alias is given below.
			Note that this is not necessarily the same as the actual statement
			used to create the alias (it has been reconstructed from the
			content of the system catalog tables and may differ in a number of
			areas)."""))
		self.add(self.pre(self.format_sql(self.dbobject.createSql), attrs={'class': 'sql'}))

