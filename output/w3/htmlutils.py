#!/bin/env python
# $Header$
# vim: set noet sw=4 ts=4:

import datetime
import HTMLParser
from xml.sax.saxutils import quoteattr, escape

class StripHTML(HTMLParser.HTMLParser):
	def strip(self, data):
		self._output = []
		self.feed(data)
		self.close()
		return ''.join(self._output)
	
	def handle_data(self, data):
		self._output.append(data)
	
	def handle_charref(self, ref):
		self._output.append(chr(int(ref)))
	
	def handle_entityref(self, ref):
		self._output.append({
			'amp': '&',
			'lt': '<',
			'gt': '>',
			'apos': "'",
			'quot': '"',
		}[ref])

def stripTags(content):
	return StripHTML().strip(content)

def startTag(name, attrs={}, empty=False):
	"""Generates an XHTML start tag containing the specified attributes"""
	subst = {
		'name': name,
		'attrs': ''.join([" %s=%s" % (str(key), quoteattr(str(attrs[key]))) for key in attrs]),
	}
	if empty:
		return "<%(name)s%(attrs)s />" % subst
	else:
		return "<%(name)s%(attrs)s>" % subst

def endTag(name):
	"""Generates an XHTML end tag"""
	return "</%s>" % (name)

def formatContent(content):
	if content is None:
		# Format None as 'n/a'
		return 'n/a'
	elif isinstance(content, datetime.datetime):
		# Format timestamps as ISO8601-ish (without the T separator)
		return content.strftime('%Y-%m-%d %H:%M:%S')
	elif type(content) in [int, long]:
		# Format integer numbers with , as a thousand separator
		s = str(content)
		for i in xrange(len(s) - 3, 0, -3): s = "%s,%s" % (s[:i], s[i:])
		return s
	else:
		return str(content)

def makeTag(name, attrs={}, content="", optional=False):
	"""Generates a XHTML element containing the specified attributes and content"""
	# Convert the content into a string, using custom conversions as necessary
	contentStr = formatContent(content)
	if contentStr != "":
		return "%s%s%s" % (startTag(name, attrs), contentStr, endTag(name))
	elif not optional:
		return startTag(name, attrs, True)
	else:
		return ""

def makeTableCaption(caption, attrs={}):
	if caption:
		return makeTag('caption', attrs, caption)
	else:
		return ''

def makeTableCell(content, head=False, attrs={}):
	"""Returns a table cell containing the specified content"""
	if type(content) == type({}):
		attrs = dict(content) # Take a copy of content
		content = attrs.get('', '')
		del attrs['']
	if str(content) != "":
		return makeTag(['td', 'th'][bool(head)], attrs, content)
	else:
		return makeTag(['td', 'th'][bool(head)], attrs, '&nbsp;')

def makeTableRow(cells, head=False, attrs={}):
	"""Returns a table row containing the specified cells"""
	if type(cells) == type({}):
		attrs = dict(cells) # Take a copy of cells
		cells = attrs.get('', [])
		del attrs['']
	return makeTag('tr', attrs, ''.join([makeTableCell(content, head) for content in cells]))

def makeTable(data, head=[], foot=[], caption='', tableAttrs={}):
	"""Returns a table containing the specified head and data cells"""
	defaultAttrs = {'class': 'basic-table', 'cellspacing': 1, 'cellpadding': 0}
	defaultAttrs.update(tableAttrs)
	return makeTag('table', defaultAttrs, ''.join([
			makeTableCaption(caption),
			makeTag('thead', {}, ''.join([makeTableRow(row, head=True, attrs={'class': 'blue-med-dark'}) for row in head]), optional=True),
			makeTag('tfoot', {}, ''.join([makeTableRow(row, head=True, attrs={'class': 'blue-med-dark'}) for row in foot]), optional=True),
			makeTag('tbody', {}, ''.join([makeTableRow(row, head=False, attrs={'class': color}) for (row, color) in zip(data, ['white', 'gray'] * len(data))]), optional=False),
		])
	)

def makeListItem(content):
	"""Returns a list item containing the specified content"""
	return makeTag('li', {}, content)

def makeOrderedList(items):
	"""Returns an ordered list containing the specified items"""
	return makeTag('ol', {}, ''.join([makeListItem(item) for item in items]))

def makeUnorderedList(items):
	"""Returns an unordered list containing the specified items"""
	return makeTag('ul', {}, ''.join([makeListItem(item) for item in items]))

def makeDefinitionList(items):
	"""Returns a definition list containing the specified items"""
	return makeTag('dl', {}, ''.join([
		''.join([
			makeTag('dt', {}, term),
			makeTag('dd', {}, definition)
		])
		for term, definition in items
	]))

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
	"""Generates a popup link to the specified target"""
	return makeTag('a', {'href': 'javascript:popup("%s","internal",%d,%d)' % (target, height, width)}, content)

def main():
	# XXX Test cases
	pass

if __name__ == "__main__":
	main()
