# vim: set noet sw=4 ts=4:

"""Output plugin for TeX documentation."""

import os
import sys
mswindows = sys.platform.startswith('win')
import logging
import db2makedoc.db
import db2makedoc.plugins
from db2makedoc.plugins.tex.document import TeXDocumentation
from db2makedoc.graph import DEFAULT_CONVERTER
from string import Template

class OutputPlugin(db2makedoc.plugins.OutputPlugin):
	"""Output plugin for TeX documentation.

	This output plugin supports generating PDF documentation via the TeX
	type-setting system, specifically the LaTeX variant (including various PDF
	facilities). It includes syntax highlighted SQL information on various
	objects in the database (views, tables, etc.), diagrams of the schema, and
	hyperlinks within generated PDFs.
	"""

	def __init__(self):
		super(OutputPlugin, self).__init__()
		self.add_option('filename', default=None, convert=self.convert_path,
			doc="""The path and filename for the TeX output file. Use $db or
			${db} to include the name of the database in the filename. The
			$dblower and $dbupper substitutions are also available, for forced
			lowercase and uppercase versions of the name respectively. To
			include a literal $, use $$""")
		self.add_option('paper_size', default='a4paper',
			doc="""The size of paper to use in the document. Must be specified
			as a TeX paper size understood by the geometry package. See your
			LaTeX distribution's geometry package for more information about
			available paper sizes""")
		self.add_option('bookmarks', default='true', convert=self.convert_bool,
			doc="""Specifies whether or not to generate bookmarks in PDF output
			(for use with pdflatex)""")
		self.add_option('binding_size', default='',
			doc="""Specifies the extra space left on the inner edge of the
			paper for binding printed output. Specified as TeX dimensions, i.e.
			an actual measurement or a TeX command. See your LaTeX
			distribution's geometry package for more information""")
		self.add_option('margin_size', default='', convert=self.convert_list,
			doc="""Specifies the paper margins as either a single dimension
			(applies to all sides), two dimensions (top & bottom, left &
			right), or four dimesions (top, right, bottom, left). Left is
			equivalent to inner, and right to outer margins when two_side is
			true. Specified as TeX dimensions, i.e. actual measurements of TeX
			commands. See your LaTeX distribution's geometry package for more
			information""")
		self.add_option('landscape', default='false', convert=self.convert_bool,
			doc="""If true, the document will default to a landscape
			orientation""")
		self.add_option('two_side', default='false', convert=self.convert_bool,
			doc="""If true, the document will use two sided output, resulting
			in mirrored margins for left and right pages""")
		self.add_option('font_packages', default='', convert=self.convert_list,
			doc="""A comma separated list of font packages to load in the
			document preamble.  Common font packages are avant, courier,
			bookman, charter, chancery, and newcent. See your LaTeX
			distribution's psnfss documentation for more information about the
			available font packages""")
		self.add_option('font_size', default='10pt',
			doc="""The default font size used by the document. Can be one of
			10pt (the default), 11pt, or 12pt""")
		self.add_option('encoding', default='utf8x',
			doc="""The character encoding to use for the TeX output file.
			Specified as a TeX encoding. See your LaTeX distribution's inputenc
			documentation for more information on available encodings""")
		self.add_option('doc_title', default='$db Documentation',
			doc="""The title of the document. Accepts $-prefixed substitutions
			(see filename)""")
		self.add_option('author_name', default='',
			doc="""The name of the author of the document""")
		self.add_option('author_email', default='',
			doc="""The e-mail address of the author of the document""")
		self.add_option('copyright', default='',
			doc="""The copyright message to embed in the document""")
		self.add_option('diagrams', default='', convert=self.convert_dbclasses,
			doc="""A comma separated list of the object types for which
			diagrams should be generated, e.g. "schemas, relations". Currently
			only diagrams of schemas and relations (tables, views, and aliases)
			are supported. Note that schema diagrams may require an extremely
			large amount of RAM (1Gb+) to process""")
		self.add_option('toc', default='true', convert=self.convert_bool,
			doc="""Specifies whether or not to generate a Table of Contents at
			the start of the document""")
		self.add_option('index', default='false', convert=self.convert_bool,
			doc="""Specifies whether or not to generate an alphabetical index
			at the end of the document""")
		self.add_option('lang', default='en-US',
			convert=lambda value: self.convert_list(value, separator='-', minvalues=2, maxvalues=2),
			doc="""The ISO639 language code indicating the language that the
			document uses.""")

	def configure(self, config):
		super(OutputPlugin, self).configure(config)
		# Ensure the filename was specified
		if not self.options['filename']:
			raise db2makedoc.plugins.PluginConfigurationError('The filename option must be specified')
		# If diagrams are requested, check we can find GraphViz in the PATH
		if self.options['diagrams']:
			gvexe = DEFAULT_CONVERTER
			if mswindows:
				gvexe = os.extsep.join([gvexe, 'exe'])
			found = reduce(lambda x,y: x or y, [
				os.path.exists(os.path.join(path, gvexe))
				for path in os.environ.get('PATH', os.defpath).split(os.pathsep)
			], False)
			if not found:
				raise db2makedoc.plugins.PluginConfigurationError('Diagrams requested, but the GraphViz utility (%s) was not found in the PATH' % gvexe)

	def substitute(self):
		"""Returns the list of options which can accept $-prefixed substitutions."""
		# Override this in descendents if additional string options are introduced
		return ('filename', 'doc_title')

	def execute(self, database):
		"""Invokes the plugin to produce documentation."""
		super(OutputPlugin, self).execute(database)
		# Take a copy of the options if we haven't already
		if not hasattr(self, 'options_templates'):
			self.options_templates = dict(self.options)
		# Build the dictionary of substitutions for $-prefixed variable
		# references in all substitutable options (path et al.)
		values = dict(os.environ)
		values.update({
			'db': database.name,
			'dblower': database.name.lower(),
			'dbupper': database.name.upper(),
			'dbtitle': database.name.title(),
		})
		self.options = dict(self.options_templates)
		for option in self.substitute():
			if isinstance(self.options[option], basestring):
				self.options[option] = Template(self.options[option]).safe_substitute(values)
		doc = TeXDocumentation(database, self.options)
		doc.write()
