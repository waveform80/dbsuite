# vim: set noet sw=4 ts=4:

"""Output plugin for IBM Intranet w3v8 style web pages."""

import db2makedoc.plugins
import db2makedoc.plugins.html
from db2makedoc.db import Schema, Table, View, Alias
from db2makedoc.plugins.html.w3.document import W3Site


class OutputPlugin(db2makedoc.plugins.html.HTMLOutputPlugin):
	"""Output plugin for IBM Intranet w3v8 style web pages.

	This output plugin supports generating XHTML documentation conforming to
	the internal IBM w3v8 style [1]. It includes syntax highlighted SQL,
	information on various objects in the database (views, tables, etc.) and
	diagrams of the schema.

	[1] http://w3.ibm.com/standards/intranet/homepage/v8/index.html
	"""

	def __init__(self):
		"""Initializes an instance of the class."""
		super(OutputPlugin, self).__init__()
		self.site_class = W3Site
		self.add_option('confidential', default='false', convert=self.convert_bool,
			doc="""If true, each page will be marked "IBM Confidential" below
			the title""")
		self.add_option('breadcrumbs', default='true', convert=self.convert_bool,
			doc="""If true, breadcrumb links will be shown at the top of each
			page""")
		self.add_option('last_updated', default='true', convert=self.convert_bool,
			doc= """If true, a line will be added to the top of each page
			showing the date on which the page was generated""")
		self.add_option('feedback_url', default='http://w3.ibm.com/feedback/',
			doc="""The URL which the feedback link at the top right of each
			page points to (defaults to the standard w3 feedback page).
			Accepts $-prefixed substitutions (see path)""")
		self.add_option('menu_items', default='', convert=self.convert_odict,
			doc="""A comma-separated list of name=url values to appear in the
			left-hand menu. The special URL # denotes the position of of the
			database document, e.g.  My App=/myapp,Data
			Dictionary=#,Admin=/admin. If the special URL does not appear in
			the list, the database document will be the last menu entry. Note
			that the "home_title" and "home_url" values are implicitly included
			at the top of this list. Accepts $-prefixed substitutions (see
			path)""")
		self.add_option('related_items', default='', convert=self.convert_odict,
			doc="""A comma-separated list of links to add after the left-hand
			menu. Links are name=url values, see the "menu_items" description
			for an example. Accepts $-prefixed substitutions (see path)""")
		self.add_option('max_graph_size', default='600x800',
			convert=lambda value: self.convert_list(value, separator='x',
			subconvert=lambda value: self.convert_int(value.strip(), minvalue=100),
			minvalues=2, maxvalues=2),
			doc="""The maximum size that diagrams are allowed to be on the
			page. If diagrams are larger, they will be resized and a zoom
			function will permit viewing the full size image. Values must be
			specified as "widthxheight", e.g. "640x480". Defaults to
			"600x800".""")
		# Tweak the default icon_url
		self.options['icon_url'] = ('http://w3.ibm.com/favicon.ico',) + self.options['icon_url'][1:]
	
	def configure(self, config):
		super(OutputPlugin, self).configure(config)
		# If diagrams are requested, check we can import PIL
		if self.options['diagrams']:
			try:
				import PIL
			except ImportError:
				raise db2makedoc.plugins.PluginConfigurationError('Diagrams requested, but the Python Imaging Library (PIL) was not found')
		supported_diagrams = set([Schema, Table, View, Alias])
		if self.options['diagrams'] - supported_diagrams:
			raise db2makedoc.plugins.PluginConfigurationError('No diagram support for %s objects (supported objects are %s)' % (
				', '.join(c.config_names[0] for c in self.options['diagrams'] - supported_diagrams),
				', '.join(c.config_names[0] for c in supported_diagrams)
			))

	def substitute(self):
		return super(OutputPlugin, self).substitute() + ('feedback_url', 'menu_items', 'related_items')
