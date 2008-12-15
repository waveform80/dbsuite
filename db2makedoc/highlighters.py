# vim: set noet sw=4 ts=4:

"""Implements generic classes for parsing of text into markup.

This module provides some base classes which can be used to parse text or
code into markup-based languages. The base classes do not assume any particular
type of markup and simply provide stub routines which can be overridden in
descendent classes to implement a specific markup language (e.g. HTML).
"""

import re
import logging
from db2makedoc.sql.tokenizer import *
from db2makedoc.sql.formatter import *

class CommentHighlighter(object):
	"""Implements a generic class for parsing simple prefix-based markup.

	This module defines a base class for converting a simple Usenet posting
	style markup into some other markup style, e.g. HTML. The class itself only
	performs recognition of the markup and defines several handler methods
	which can be overridden in descendents to perform the actual conversion.
	The syntax of the input markup is as follows:

	* A word surrounded by *asterisks* is strong (e.g. bold).
	* A word surrounded by /slash/ is emphasized (e.g. italic).
	* A word surrounded by _underscores_ is underlined.
	* An identifier, possibly compound, prefixed by @ is a pointer to a
	  database object (e.g. @SYSCAT.TABLES).
	* A line break (\\n) indicates the end of a paragraph.

	As the markup is intended for use in the comments attached to meta-data in
	the database (which has extremely limited field sizes), it is designed to
	be minimal and unobtrusive to the eye when read prior to conversion.
	"""

	find_ref = re.compile(r'@([A-Za-z_$#@][\w$#@]*(\.[A-Za-z_$#@][\w$#@]*){0,2})\b')
	find_fmt = re.compile(r'(^|[\s\W])([/_*])(\w+)\2($|[\s\W])')

	def start_parse(self, summary):
		"""Stub handler for parsing start."""
		self._content = []

	def start_para(self):
		"""Stub handler for paragraph starts."""
		self._para = ''

	def handle_text(self, text):
		"""Stub handler for plain text."""
		self._para += text

	def handle_strong(self, text):
		"""Stub handler for strong/bold text."""
		self.handle_text('*%s*' % text)

	def handle_emphasize(self, text):
		"""Stub handler for emphasized/italic text."""
		self.handle_text('/%s/' % text)

	def handle_underline(self, text):
		"""Stub handler for underlined text."""
		self.handle_text('_%s_' % text)

	def find_target(self, name):
		"""Stub handler to find a database object given its name."""
		return None

	def handle_link(self, target):
		"""Stub handler for link references."""
		self.handle_text('@%s' % target.qualified_name)

	def end_para(self):
		"""Stub handler for paragraph ends."""
		self._content.append(self._para)

	def end_parse(self, summary):
		"""Stub handler for parsing end."""
		return '\n\n'.join(self._content)
	
	def parse(self, text, summary=False):
		"""Converts the provided text into another markup language.

		The summary parameter, if True, indicates that only the first line of
		the text should be marked up and returned.
		"""
		self.start_parse(summary)
		paras = text.split('\n')
		if summary:
			paras = [paras[0]]
		for para in paras:
			if len(para) == 0:
				continue
			self.start_para()
			start = 0
			while True:
				match_ref = self.find_ref.search(para, start)
				match_fmt = self.find_fmt.search(para, start)
				if match_ref is not None and (match_fmt is None or match_fmt.start(2) > match_ref.start(0)):
					self.handle_text(para[start:match_ref.start(0)])
					start = match_ref.end(0)
					target = self.find_target(match_ref.group(1))
					if target is None:
						logging.warning('Failed to find database object %s referenced in comment: "%s"' % (match_ref.group(1), text))
						self.handle_text(match_ref.group(0))
					else:
						self.handle_link(target)
				elif match_fmt is not None and (match_ref is None or match_fmt.start(2) < match_ref.start(0)):
					self.handle_text(para[start:match_fmt.start(2)])
					start = match_fmt.start(4)
					if match_fmt.group(2) == '*':
						self.handle_strong(match_fmt.group(3))
					elif match_fmt.group(2) == '/':
						self.handle_emphasize(match_fmt.group(3))
					elif match_fmt.group(2) == '_':
						self.handle_underline(match_fmt.group(3))
					else:
						assert False
				else:
					self.handle_text(para[start:])
					break
			self.end_para()
		return self.end_parse(summary)


class SQLHighlighter(object):
	"""Implements a generic class for highlighting SQL with markup.

	This unit defines a base class for converting an SQL string or script into
	a markup language, e.g. HTML. Output plugins can sub-class this to generate
	their own particular markup.

	The class utilizes the tokenizer and (optionally) formatter classes from
	the sql module to parse the SQL and defines various handler stubs for
	converting the result tokens into markup.
	"""

	def __init__(self):
		"""Initializes an instance of the class"""
		super(SQLHighlighter, self).__init__()
		# XXX At some point we need to implement a mechanism for the input
		# plugin to inform this what tokenizer and formatter to use (although
		# there's not much point until other formatters are developed ;-)
		self.tokenizer = DB2LUWTokenizer()
		self.formatter = DB2LUWFormatter()
	
	def format_line(self, index, line):
		"""Stub handler for a line of tokens"""
		return ''.join(self.format_token(token) for token in line)

	def format_token(self, token):
		"""Stub handler for a token"""
		return token[2]
	
	def parse(self, sql, terminator=';', line_split=False):
		"""Converts the provided SQL into another markup language.

		The sql parameter contains the SQL to be converted into markup. The
		optional terminator parameter specifies the intial statement terminator
		assumed to be used in the SQL code (defaults to semi-colon).
		
		Finally, if the optional line_split parameter is False (which it is by
		default), the SQL will be returned as a list of marked up strings where
		each string is a single token in the input. If line_split is True, the
		SQL will be returned as a list of marked up strings where each string
		is a single line of tokens in the input. This provides the opportunity
		for descendent classes to perform by-line handling, e.g. converting the
		SQL into a two-column table with line numbers in the left column.
		"""
		def excerpt(tokens):
			if len(tokens) > 10:
				excerpt = tokens[:10] + [(0, None, '...', 0, 0)]
			else:
				excerpt = tokens
			return ''.join(token[2] for token in excerpt)

		self.formatter.line_split = line_split
		tokens = self.tokenizer.parse(sql, terminator, line_split)
		# Check for errors in the tokens
		errors = [token for token in tokens if token[0] == ERROR]
		if errors:
			# If errors were found, log a warning for each error and return the
			# SQL highlighted from the tokenized stream without reformatting
			logging.warning('While tokenizing %s' % excerpt(tokens))
			for error in errors:
				logging.warning('error %s found at line %d, column %d' % (error[1], error[3], error[4]))
		else:
			# If the SQL tokenized successfully, attempt to reformat it nicely
			# but if an error occurs, just warn about it and continue with the
			# SQL highlighted from the tokenized stream
			try:
				tokens = self.formatter.parse(tokens)
			except ParseTokenError, e:
				logging.warning('While formatting %s' % excerpt(tokens))
				logging.warning('error %s found at line %d, column %d' % (e.message, e.line, e.col))
		# Both the tokenizer and formatter always return at least one token (an
		# EOF token). Hence, if the first token is EOF, the source is blank
		if tokens[0][0] != EOF:
			if line_split:
				return (
					self.format_line(line + 1, (token for token in tokens if token[3] == line + 1))
					for line in xrange(tokens[-1][3])
				)
			else:
				return (self.format_token(token) for token in tokens)
		else:
			return ()
	
	def parse_prototype(self, sql):
		"""Utility routine for marking up a routine prototype (as opposed to a complete SQL script)"""
		self.tokenizer.line_split = False
		self.formatter.line_split = False
		tokens = self.formatter.parse_routine_prototype(self.tokenizer.parse(sql))
		return [self.format_token(token) for token in tokens]
	
	def parse_to_string(self, sql, terminator=';', line_split=False):
		"""Utility routine which returns the result of parse() as a single string"""
		return ''.join(self.parse(sql, terminator, line_split))
	
	def parse_prototype_to_string(self, sql):
		"""Utility routine which returns the result of parse_prototype() as a single string"""
		return ''.join(self.parse_prototype(sql))
