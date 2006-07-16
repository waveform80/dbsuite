#!/usr/bin/env python
# $Header$
# vim: set noet sw=4 ts=4:

import xml.dom
import xml.dom.minidom
import db.base
import output.html

class W3Site(output.html.HTMLSite):
	"""Site class representing a collection of W3Document instances."""

	def __init__(self, database):
		"""Initializes an instance of the class."""
		super(W3Site, self).__init__()
		self.database = database
		self.title = '%s Documentation' % self.database.name
		self.keywords = [self.database.name]
		self.copyright = 'Copyright (c) 2001,2006 by IBM corporation'
		self.document_map = {}
		# Template of the <body> element of a w3v8 document. This is parsed
		# into a DOM tree, grafted onto the generated document and then filled
		# in by searching for elements by id in the create_content() method of
		# the W3Document class below.
		self.template = """<?xml version="1.0" encoding="ISO-8859-1"?>
<!DOCTYPE html
	PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
	"http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="en" xml:lang="en">
<head>
</head>
<body id="w3-ibm-com" class="article">

<!-- start accessibility prolog -->
<div class="skip"><a href="#content-main" accesskey="2">Skip to main content</a></div>
<div class="skip"><a href="#left-nav" accesskey="n">Skip to navigation</a></div>
<div id="access-info">
	<p class="access">The access keys for this page are:</p>
	<ul class="access">
		<li>ALT plus 0 links to this site's <a href="http://w3.ibm.com/w3/access-stmt.html" accesskey="0">Accessibility Statement.</a></li>
		<li>ALT plus 1 links to the w3.ibm.com home page.</li>
		<li>ALT plus 2 skips to main content.</li>
		<li>ALT plus 4 skips to the search form.</li>
		<li>ALT plus 9 links to the feedback page.</li>
		<li>ALT plus N skips to navigation.</li>
	</ul>
	<p class="access">Additional accessibility information for w3.ibm.com can be found <a href="http://w3.ibm.com/w3/access-stmt.html">on the w3 Accessibility Statement page.</a></p>
</div>
<!-- end accessibility prolog -->

<!-- start masthead -->
<div id="masthead">
	<h2 class="access">Start of masthead</h2>
	<div id="prt-w3-sitemark"><img src="//w3.ibm.com/ui/v8/images/id-w3-sitemark-simple.gif" alt="" width="54" height="33" /></div>
	<div id="prt-ibm-logo"><img src="//w3.ibm.com/ui/v8/images/id-ibm-logo-black.gif" alt="" width="44" height="15" /></div>
	<div id="w3-sitemark"><img src="//w3.ibm.com/ui/v8/images/id-w3-sitemark-large.gif" alt="IBM Logo" width="266" height="70" usemap="#sitemark_map" /><map id="sitemark_map" name="sitemark_map"><area shape="rect" alt="Link to W3 Home Page" coords="0,0,130,70" href="http://w3.ibm.com/"  accesskey="1" /></map></div>
	<div id="site-title-only" />
	<div id="ibm-logo"><img src="//w3.ibm.com/ui/v8/images/id-ibm-logo.gif" alt="" width="44" height="15" /></div>
	<div id="persistent-nav"><a id="w3home" href="http://w3.ibm.com/"> w3 Home </a><a id="bluepages" href="http://w3.ibm.com/bluepages/"> BluePages </a><a id="helpnow" href="http://w3.ibm.com/help/"> HelpNow </a><a id="feedback" href="http://w3.ibm.com/feedback/" accesskey="9"> Feedback </a></div>
	<div id="header-search">
		<form action="http://w3.ibm.com/search/w3results.jsp" method="get" id="search">
		<table cellspacing="0" cellpadding="0" class="header-search">
		<tr><td class="label"><label for="header-search-field">Search w3</label></td><td class="field"><input id="header-search-field" name="qt" type="text" accesskey="4" /></td><td class="submit"><label class="access" for="header-search-btn">go button</label><input id="header-search-btn" type="image" alt="Go" src="//w3.ibm.com/ui/v8/images/btn-go-dark.gif" /></td></tr>
		</table>
		</form>
	</div>
	<div id="browser-warning"><img src="//w3.ibm.com/ui/v8/images/icon-system-status-alert.gif" alt="" width="12" height="10" /> This Web page is best used in a modern browser. Since your browser is no longer supported by IBM, please upgrade your web browser at the <a href="http://w3.ibm.com/download/standardsoftware/">ISSI site</a>.</div>
</div>
<!-- stop masthead -->

<!-- start content -->
<div id="content">
	<h1 class="access">Start of main content</h1>

	<!-- start content head -->
	<div id="content-head">
		<p id="date-stamp" />
		<div class="hrule-dots">&nbsp;</div>    
		<p id="breadcrumbs" />
	</div>
	<!-- stop content head -->

	<!-- start main content -->
	<div id="content-main">
		<p class="terms"><a href="http://w3.ibm.com/w3/info_terms_of_use.html">Terms of use</a></p>
	</div>
	<!-- stop main content -->

</div>
<!-- stop content -->

<!-- start navigation -->
<div id="navigation">
	<h2 class="access">Start of left navigation</h2>

	<!-- left nav -->
	<div id="left-nav">
	</div>

	<!-- start related links -->
	<p>Related links:</p>
	<ul>
		<li><a href="http://isls.endicott.ibm.com/Documentation/nw3Doc.htm">IS&amp;LS Documentation Home</a></li>
		<li><a href="http://isls5.endicott.ibm.com/bmsiwIC/index.html">BMS/IW Reference</a></li>
		<li><a href="http://bmt.stuttgart.de.ibm.com/">BMT Homepage</a></li>
		<li><a href="https://servicesim.portsmouth.uk.ibm.com/cgi-bin/db2www/~bmtdoc/docu_bmt.mac/report">BMT Dynamic Documentation</a></li>
	    <li><a href="http://publib.boulder.ibm.com/infocenter/db2luw/v8/index.jsp">IBM DB2 UDB Info Center</a></li>
	</ul>
	<!-- stop related links -->

</div>
<!-- stop navigation -->

</body>
</html>
"""

class W3Document(output.html.HTMLDocument):
	"""Document class representing a database object (table, view, index, etc.)"""

	def __init__(self, site, dbobject, htmlver=XHTML10, htmlstyle=STRICT):
		"""Initializes an instance of the class.

		Parameters:
		dbobject -- The database object that this document covers
		htmlver -- Version of HTML to use when writing out the document
		htmlstyle -- Specific style of the HTML DTD to use when writing the document
		"""
		assert isinstance(site, W3Site)
		super(W3Document, self).__init__('%s.html' % dbobject.identifier, htmlver, htmlstyle)
		self.dbobject = dbobject
		self.site.document_map[dbobject] = self
		self.title = '%s - %s %s' % (self.site.title, self.dbobject.typeName, self.dbobject.qualifiedName)
		self.description = '%s %s' % (self.dbobject.typeName, self.dbobject.qualifiedName)
		self.keywords = [self.site.database.name, self.dbobject.typeName, self.dbobject.name, self.dbobject.qualifiedName]
	
	def write(self, path, pretty=True):
		# Overridden to add logging
		logging.debug('Writing documentation for %s %s to %s.html' %
			(self.dbobject.typeName, self.dbobject.name, os.path.join(path, self.dbobject.identifier)))
		super(W3Document, self).write(path, pretty)

	def create_content(self):
		# Overridden to automatically set the link objects and generate the
		# content from the sections filled in by descendent classes in
		# create_sections
		if not self.link_first:
			self.link_first = self.site.document_map.get(self.dbobject.first)
		if not self.link_prior:
			self.link_prior = self.site.document_map.get(self.dbobject.prior)
		if not self.link_next:
			self.link_next = self.site.document_map.get(self.dbobject.next)
		if not self.link_last:
			self.link_last = self.site.document_map.get(self.dbobject.last)
		if not self.link_up:
			self.link_up = self.site.document_map.get(self.dbobject.parent)
		# Call the inherited method to create the skeleton document
		super(W3Document, self).create_content()
		# Add stylesheets and scripts specific to the w3v8 style
		headnode = self.doc.getElementsByTagName('head')[0]
		headnode.appendChild(self.meta('IBM.Country', 'US'))
		headnode.appendChild(self.meta('IBM.Effective', self.date.strftime('%Y-%m-%d'), 'iso8601'))
		headnode.appendChild(self.script(src='//w3.ibm.com/ui/v8/scripts/scripts.js'))
		headnode.appendChild(self.style(src='//w3.ibm.com/ui/v8/css/v4-screen.css'))
		headnode.appendChild(self.style(content="""
		<!--
			@import url("//w3.ibm.com/ui/v8/css/screen.css");
			@import url("//w3.ibm.com/ui/v8/css/icons.css");
			@import url("//w3.ibm.com/ui/v8/css/tables.css");
			@import url("//w3.ibm.com/ui/v8/css/interior.css");
			@import url("//w3.ibm.com/ui/v8/css/interior-1-col.css");
		-->""", media='all'))
		headnode.appendChild(self.style(src='sql.css', media='all'))
		headnode.appendChild(self.style(src='//w3.ibm.com/ui/v8/css/print.css', media='print'))
		# Parse the HTML in template and graft the <body> element onto the
		# <body> element in self.doc
		template = xml.dom.minidom.parseString(self.site.template)
		oldbodynode = self.doc.getElementsByTagName('body')[0]
		newbodynode = template.getElementsByTagName('body')[0]
		newbodynode = self.doc.importNode(newbodynode, deep=True)
		template.unlink()
		self.doc.documentElement.replaceChild(newbodynode, oldbodynode)
		# Fill in the template
		self.append_content(self.find_element('div', 'site-title-only'), '%s Documentation' % self.dbobject.database.name)
		self.append_content(self.find_element('p', 'date-stamp'), 'Updated on %s' % self.date.strftime('%a, %d %b %Y'))
		self.create_crumbs()
		self.create_menu()
		self.sections = []
		self.create_sections()
		mainnode = self.find_element('div', 'content-main')
		mainnode.appendChild(self.hr())
		mainnode.appendChild(self.h('%s %s' % (self.dbobject.typeName, self.dbobject.qualifiedName), level=1))
		mainnode.appendChild(self.ul([self.a('#%s' % section['id'], section['title'], 'Jump to section') for section in self.sections]))
		for section in self.sections:
			mainnode.appendChild(self.hr())
			mainnode.appendChild(self.h(section['title'], level=2))
			self.append_content(mainnode, section['content'])
			mainnode.appendChild(self.p(self.a('#masthead', 'Back to top', 'Jump to top')))
	
	def create_menu(self):
		"""Creates the content of left-hand navigation menu."""
		
		def make_menu_level(self, selitem, active, subitems):
			"""Builds a list of menu items for a database object and its siblings.

			The make_menu_level() subroutine is called with a database object
			(e.g. a field, table, schema, etc) and returns a list of tuples
			consisting of (url, content, title, active, [children]).
			
			This tuple will eventually be converted into an anchor link, hence
			url will become the href of the link, content will become the text
			content of the link, title will be the value of the title
			attribute, and the boolean active value will indicate whether the
			class "active" is applied to the link. Finally [children] is a list
			of similarly structured tuples giving the entries below the
			corresponding entry.

			Parameters:
			selitem -- The database object to generate menu items around
			active -- True if the database object is the focus of the document (and hence, selected)
			subitems -- The child entries of selitem (if any)
			"""
			moretop = False
			morebot = False
			if selitem.parentList is None:
				slice = [selitem]
			else:
				index = selitem.parentIndex
				if len(selitem.parentList) <= 10:
					slice = selitem.parentList
				elif index <= 3:
					slice = selitem.parenList[:7]
					morebot = True
				elif index >= len(selitem.parentList) - 4:
					slice = selitem.parentList[-7:]
					moretop = True
				else:
					slice = selitem.parentList[index - 3:index + 4]
					moretop = True
					morebot = True
			# items is a list of tuples of (URL, content, title, active, [children])
			items = []
			for item in slice:
				content = item.name
				if len(content) > 10: content = '%s...' % content[:10]
				title = '%s %s' % (item.typeName, item.qualifiedName)
				if item == selitem:
					items.append((self.site.document_map[item].url, content, title, active, subitems))
				else:
					items.append((self.site.document_map[item].url, content, title, False, []))
			if moretop:
				items.insert(0, ('#', u'\u2191 More items...', 'More items', False, [])) # \u2191 == &uarr;
			if morebot:
				items.append(('#', u'\u2193 More items...', 'More items', False, [])) # \u2193 == &darr;
			return items

		def make_menu_tree(self, item, active=True):
			"""Builds a tree of menu items for a given database object.

			The make_menu_tree() sub-routine, given a database object, builds a
			tree of tuples (structured as a list of tuples of lists of tuples,
			etc). The tuples are structured as in the make_menu_level
			sub-routine above.

			The tree is built "bottom-up" starting with the selected item (the
			focus of the document being produced) then moving to the parent of
			that item and so on, until the top level is reached.

			Parameters:
			item -- The item to construct a menu tree for
			active -- (optional) If True, item is the focus of the document (and hence, selected)
			"""
			# items is a list of tuples of (URL, content, title, active, [children])
			items = []
			while item is not None:
				items = make_menu_level(item, active, items)
				active = False
				item = item.parent
			items.insert(0, 'index.html', 'Home', 'Home', False, [])
			return items

		def make_menu_dom(self, parent, items, level=0):
			"""Builds the actual DOM link elements for the menu.

			The make_menu_dom() sub-routine takes the output of the
			make_menu_tree() subroutine and converts it into actual DOM
			elements. This is done in a "top-down" manner (the reverse of
			make_menu_tree()) in order to easily calculate the current nesting
			level (this also explains the separation of make_menu_tree() and
			make_menu_dom()).

			Parameters:
			parent -- The DOM node which will be the parent of the menu elements
			items -- The output of the make_menu_tree() subroutine
			level -- (optional) The current nesting level
			"""
			classes = ['top-level', 'second-level', 'third-level']
			parent = parent.appendChild(self.doc.createElement('div'))
			parent.setAttribute('class', classes[level])
			for (url, content, title, active, children) in items:
				link = parent.appendChild(self.a(url, content, title))
				if active:
					link.setAttribute('class', 'active')
				if len(children) > 0:
					make_menu_elements(link, children, level + 1)

		make_menu_dom(self.find_element('div', 'left-nav'), make_menu_tree(self.dbobject))

	def create_crumbs(self):
		"""Creates the breadcrumb links at the top of the page."""
		crumbs = []
		item = self.dbobject
		while item is not None:
			crumbs.insert(0, self.a_to(item, typename=True, qualifiedname=False))
			crumbs.insert(0, self.doc.createTextNode(u' \u00BB ')) # \u00BB == &raquo;
			item = item.parent
		crumbs.insert(0, self.a('index.html', 'Home'))
		self.append_content(self.find_element('p', 'breadcrumbs'), crumbs)
	
	# CONTENT METHODS
	# The following methods are for use in descendent classes to fill the
	# sections list with content. Basically, all descendent classes need to do
	# is override the create_sections() method, calling section() and add() in
	# their implementation

	def create_sections(self):
		# Override in descendent classes
		pass

	def section(self, id, title):
		"""Starts a new section in the body of the current document.

		Parameters:
		id -- The id of the anchor at the start of the section
		title -- The title text of the section
		"""
		self.sections.append({'id': id, 'title': title, 'content': []})
	
	def add(self, content):
		"""Add HTML content or elements to the end of the current section.

		Parameters:
		content -- A string, Node, NodeList, or tuple/list of Nodes
		"""
		self.sections[-1]['content'].append(content)
	
	# HTML CONSTRUCTION METHODS
	# Overridden versions specific to w3 formatting
	
	def a(self, href, content, title=None, attrs={}, popup=False, width=400, height=300):
		# Overridden to add a popup parameter
		if popup:
			href = 'javascript:popup("%s","internal",%d,%d)' % (href, height, width)
		return super(W3Document, self).a(href, content, title, attrs)

	def a_to(self, dbobject, typename=False, qualifiedname=False):
		# Special version of "a" to create a link to a database object
		assert isinstance(dbobject, db.base.DocBase)
		href = self.site.document_map[dbobject].url
		if qualifiedname:
			content = dbobject.qualifiedname
		else:
			content = dbobject.name
		if typename:
			content = '%s %s' % (dbobject.typeName, content)
		return self.a(href, content)

	def hr(self, attrs={}):
		# Overridden to use the w3 dotted blue line style (uses <div> instead of <hr>)
		return self.element('div', AttrDict(class='hrule-dots') + attrs, u'\u00A0') # \u00A0 == &nbsp;
	
	def table(self, data, head=[], foot=[], caption='', attrs={}):
		# Overridden to color alternate rows white & gray and to apply the
		# 'title' class to all header rows
		tablenode = super(W3Document, self).table(data, head, foot, caption, attrs)
		try:
			theadnode = tablenode.getElementsByTagName('thead')[0]
		except:
			theadnode = None
		if theadnode:
			for rownode in theadnode.getElementsByTagName('tr'):
				classes = rownode.getAttribute('class').split()
				classes.append('title')
				rownode.setAttribute('class', ' '.join(classes))
		try:
			tfootnode = tablenode.getElementsByTagName('tfoot')[0]
		except:
			tfootnode = None
		if tfootnode:
			for rownode in tfootnode.getElementsByTagName('tr'):
				classes = rownode.getAttribute('class').split()
				classes.append('title')
				rownode.setAttribute('class', ' '.join(classes))
		# The <tbody> element is mandatory, no try..except necessary
		colors = ['white', 'gray']
		tbodynode = tablenode.getElementsByTagName('tbody')[0]
		for (index, rownode) in enumerate(tbodynode.getElementsByTagName('tr')):
			classes = rownode.getAttribute('class').split()
			classes.append(colors[index % 2])
			rownode.setAttribute('class', ' '.join(classes))
		return tablenode

