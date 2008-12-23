# vim: set noet sw=4 ts=4:

"""Implements a highly configurable SQL tokenizer.

This unit implements a configurable SQL tokenizer base class (SQLTokenizerBase)
and several classes descended from this which implement parsing specific
dialects of SQL, and their particular oddities.

A number of classes which tokenize specific SQL dialects are derived from the
base SQLTokenizer class. Currently the following classes are defined:

SQLTokenizerBase -- Base tokenizer class
SQL92Tokenizer   -- ANSI SQL-92
SQL99Tokenizer   -- ANSI SQL-99
SQL2003Tokenizer -- ANSI SQL-2003
DB2LUWTokenizer  -- IBM DB2 for Linux/UNIX/Windows
DB2ZOSTokenizer  -- IBM DB2 for z/OS
"""

import re
import sys
import codecs
from decimal import Decimal
from db2makedoc.sql.dialects import *

__all__ = [
	'EOF',
	'ERROR',
	'WHITESPACE',
	'COMMENT',
	'KEYWORD',
	'IDENTIFIER',
	'NUMBER',
	'STRING',
	'OPERATOR',
	'LABEL',
	'PARAMETER',
	'TERMINATOR',
	'new_tokens',
	'SQLTokenizerBase',
	'SQL92Tokenizer',
	'SQL99Tokenizer',
	'SQL2003Tokenizer',
	'DB2LUWTokenizer',
	'DB2ZOSTokenizer',
]

utf8decoder = codecs.getdecoder('UTF-8')
utf8decode = lambda s: utf8decoder(s)[0]

_tokenval = 0

def new_token():
	"""Returns a new token value which is guaranteed to be unique"""
	global _tokenval
	_tokenval += 1
	return _tokenval

def new_tokens(count):
	"""Generator function for creating multiple new token values"""
	for i in range(count):
		yield new_token()

# Token constants
(
	EOF,           # End of data
	ERROR,         # Invalid/unknown token
	WHITESPACE,    # Whitespace
	COMMENT,       # A comment
	KEYWORD,       # A reserved keyword (SELECT/UPDATE/INSERT/etc.)
	IDENTIFIER,    # A quoted or unquoted identifier
	NUMBER,        # A numeric literal
	STRING,        # A string literal
	OPERATOR,      # An operator
	LABEL,         # A procedural label
	PARAMETER,     # A colon-prefixed or simple qmark parameter
	TERMINATOR,    # A statement terminator
) = new_tokens(12)

class SQLTokenizerBase(object):
	"""Base SQL tokenizer class.

	This base tokenizer class is used to convert a string containing SQL source
	code into a list of "tokens". See the parse() method for more information
	on the structure of tokens.

	Various options are available to customize the behaviour of the tokenizer
	(primarily to ease implementation of the dialect-specific subclasses,
	though they may be of use in other situations):

	keywords       The set of words that are to be treated as reserved
	               keywords.
	identchars     The set of characters that can appear in an unquoted
	               identifier. Note that the parser automatically excludes
	               numerals from this set for the initial character of an
	               identifier.
	sql_comments   If True (the default), SQL style comments (--..EOL) will be
	               recognized.
	c_comments     If True, C style comments (/*..*/) will be recognized.
	cpp_comments   If True, C++ style comments (//..EOL) will be recognized.
	multiline_str  If True (the default), string literals will be permitted to
	               span lines.
	"""

	def __init__(self):
		self.keywords = set(sql92_keywords)
		self.identchars = set(sql92_identchars)
		self.spacechars = ' \t\r\n'
		self.sql_comments = True
		self.c_comments = False
		self.cpp_comments = False
		self.multiline_str = True

	def parse(self, sql, terminator=';', line_split=False):
		"""Parses the provided source into a list of token tuples.

		This is the only public method of the tokenizer class, called to
		tokenize the provided source.  The method returns a list of 5-element
		tuples with the following structure:

			(type, value, source, line, column)

		Where type is one of the token constants described below, value is the
		"value" of the token (depends on type, see below), source is the
		characters from sql parsed to construct the token, and line and column
		provide the 1-based line and column of the start of the source element
		in sql. All source elements can be concatenated to reconstruct the
		original source verbatim. Hence:

			tokens = SQLTokenizer().tokenize(sql)
			sql == ''.join([source for (_, _, source, _, _) in tokens])

		Depending on token_type, token_value has different values:

			EOF            None
			ERROR          A descriptive error message
			WHITESPACE     None
			COMMENT        The content of the comment (excluding delimiters)
			KEYWORD        The keyword folded into uppercase
			IDENTIFIER     The identifier folded into uppercase if it was
			               unquoted in the source, or in original case if it
			               was quoted in some fashion in the source
			LABEL          Same as IDENTIFIER
			NUMBER         The value of the number. In all cases the number is
			               returned as a Decimal to avoid range and rounding problems
			STRING         The content of the string (unquoted and unescaped)
			OPERATOR       The operator
			PARAMETER      The name of the parameter if it was a colon-prefixed
			               named parameter in the source, or None for anonymous
			               parameters
			TERMINATOR     None

		The sql parameter specifies the SQL script to tokenize. The optional
		terminator parameter specifies the character or string used to separate
		top-level statements in the script. The optional line_split parameter
		specifies whether multiline tokens will be split in the output. If
		False (the default), multi-line tokens will be returned as a single
		token - hence, one can assume WHITESPACE or COMMENT tokens will never
		be immediately followed by another token of the same type. If True,
		tokens will be split at line breaks to ensure every line has a token
		with column 1 (useful when performing per-line processing on the
		result).
		"""
		self._source = sql
		self._index = 0
		self._markedindex = -1
		self._line = 1
		self._linestart = 0
		self._tokenstart = 0
		self._tokenline = self.line
		self._tokencolumn = self.column
		self._tokens = []
		self._init_jump()
		# Note that setting terminator must be done AFTER initializing the jump
		# table as doing so re-writes elements within that table. The
		# terminator is not handled within _init_jump as some dialects may
		# permit changes to the terminator in the middle of a script.
		# Descendents of this class wishing to implement such behaviour simply
		# need to set the terminator property during tokenizing.
		self._terminator = None
		self._savedhandler = None
		self.terminator = terminator
		# Loop over the sql using the jump table to parse characters (note:
		# Python strings aren't null terminated; the char property simply
		# returns a null character when _index moves beyond the end of the
		# string)
		while self.char != '\0':
			self._jump.get(self.char, self._handle_default)()
		self._add_token(EOF, None)
		# If line_split is True, split up any tokens that cross line breaks
		# (much easier to do it here than in the tokenizer itself)
		if line_split:
			result = []
			for token in self._tokens:
				(type, value, source, line, column) = token
				while '\n' in source:
					if isinstance(value, basestring) and '\n' in value:
						i = value.index('\n') + 1
						newvalue = value[:i]
						value = value[i:]
					else:
						newvalue = value
					i = source.index('\n') + 1
					newsource = source[:i]
					source = source[i:]
					result.append((type, newvalue, newsource, line, column))
					line += 1
					column = 1
				result.append((type, value, source, line, column))
			self._tokens = result
		return self._tokens

	def _init_jump(self):
		"""Initializes a dictionary of character handlers."""
		self._jump = {}
		for char in self.spacechars:
			self._jump[char] = self._handle_space
		for char in self.identchars:
			self._jump[char] = self._handle_ident
		# If numerals were included in identchars above, they will be
		# overwritten by the next bit (numerals are never permitted as the
		# first character in an unquoted identifier)
		for char in '0123456789':
			self._jump[char] = self._handle_digit
		# Add jump entries for symbols. Descendent classes will add extra
		# symbols that they handle after this
		self._jump.update({
			'(': self._handle_open_parens,
			')': self._handle_close_parens,
			'+': self._handle_plus,
			'-': self._handle_minus,
			'*': self._handle_asterisk,
			'/': self._handle_slash,
			'.': self._handle_period,
			',': self._handle_comma,
			':': self._handle_colon,
			'?': self._handle_question,
			'<': self._handle_less,
			'=': self._handle_equal,
			'>': self._handle_greater,
			"'": self._handle_apos,
			'"': self._handle_quote,
			'|': self._handle_bar,
			';': self._handle_semicolon,
		})

	def _add_token(self, tokentype, tokenvalue):
		self._tokens.append((
			tokentype,
			tokenvalue,
			self._source[self._tokenstart:self._index],
			self._tokenline,
			self._tokencolumn
		))
		self._tokenstart = self._index
		self._tokenline = self.line
		self._tokencolumn = self.column

	def _next(self, count=1):
		"""Moves the position of the tokenizer forward count positions.

		The _index variable should never be modified directly by handler
		methods. Likewise, the _source variable should never be directly read
		by handler methods. Instead, use the next() method and the char and
		nextchar properties. The next() method keeps track of the current line
		and column positions, while the char property handles reporting all
		line breaks (CR, CR/LF, or just LF) as plain LF characters (making
		handler coding easier).
		"""
		while count > 0:
			count -= 1
			if self._source[self._index] == '\r':
				if self._source[self._index + 1] == '\n':
					self._index += 2
				else:
					self._index += 1
				self._line += 1
				self._linestart = self._index
			elif self._source[self._index] == '\n':
				self._index += 1
				self._line += 1
				self._linestart = self._index
			else:
				self._index += 1

	def _mark(self):
		"""Marks the current position in the source for later retrieval.

		The mark() method is used with the markedchars property. A handler can
		call mark to save the current position in the source code, then query
		markedchars to obtain a string of all characters from the marked
		position to the current position (assuming the handler has moved the
		current position forward since calling mark().

		The markedtext property handles converting all line breaks to LF (like
		the next() method and char/nextchar properties).
		"""
		self._markedindex = self._index

	def _get_char(self):
		"""Returns the current character at the position of the tokenizer.

		The _get_char() method returns the character in _source at _index, but
		converts all line breaks to a single LF character as this makes handler
		code slightly easier to write.
		"""
		try:
			if self._source[self._index] == '\r':
				return '\n'
			else:
				return self._source[self._index]
		except IndexError:
			return '\0'

	def _get_next_char(self):
		"""Returns the character the next position of the tokenizer.

		The _get_next_char() method returns the character immediately after the
		current character in _source, and (like _get_char()) handles converting
		all line breaks into single LF characters.
		"""
		try:
			if self._source[self._index] == '\r':
				if self._source[self._index + 1] == '\n':
					if self._source[self._index + 2] == '\r':
						return '\n'
					else:
						return self._source[self._index + 2]
				else:
					return self._source[self._index + 1]
			elif self._source[self._index + 1] == '\r':
				return '\n'
			else:
				return self._source[self._index + 1]
		except IndexError:
			return '\0'

	def _get_marked_chars(self):
		"""Returns the characters from the marked position to the current.

		After calling _mark() at a starting position, a handler can later use
		_get_marked_chars() to retrieve all characters from that marked position
		to the current position (useful for extracting the content of large
		blocks of code like comments, strings, etc).
		"""
		assert self._markedindex >= 0
		return self._source[self._markedindex:self._index].replace('\r\n', '\n').replace('\r', '\n')

	def _get_line(self):
		"""Returns the current 1-based line position."""
		return self._line

	def _get_column(self):
		"""Returns the current 1-based column position."""
		return (self._index - self._linestart) + 1

	def _get_terminator(self):
		"""Returns the current statement terminator string (or character)."""
		return self._terminator

	def _set_terminator(self, value):
		"""Sets the current statement terminator string (or character).

		The _set_terminator() method sets the current terminator string (or
		character), and updates the internal jump table as necessary.
		"""
		if not value:
			raise ValueError("Statement terminator string must contain at least one character")
		# Restore the saved handler, if necessary. We don't need to do this
		# if there was no prior terminator (such as in a new instance of
		# the class). If the saved handler is the default handler (None),
		# simply remove the first character of the terminator from the jump
		# table
		if self._terminator is not None:
			if self._savedhandler is None:
				del self._jump[self._terminator[0]]
			else:
				self._jump[self._terminator[0]] = self._savedhandler
		# Replace the handler (if any) for the statement terminator
		# character (or the first character of the statement terminator
		# string) with a special handler and save the original handler for
		# use by the special handler
		if (value == '\r\n') or (value == '\r'):
			value = '\n'
		self._terminator = value
		self._savedhandler = self._jump.get(value[0])
		self._jump[value[0]] = self._handle_terminator

	char = property(_get_char)
	nextchar = property(_get_next_char)
	markedchars = property(_get_marked_chars)
	line = property(_get_line)
	column = property(_get_column)
	terminator = property(_get_terminator, _set_terminator)

	def _extract_string(self, multiline):
		"""Extracts a quoted string from the source code.

		Returns the content of a quoted string in the source code. The current
		position (in _index) is assumed to be the opening quote of the string
		(either ' or " although the function doesn't confirm this). Quotation
		characters can be escaped within the string by doubling, for example:

			'Doubled ''quotation'' characters'

		The method returns the unescaped content of the string. Hence, in the
		case above the method would return "Doubled 'quotation' characters"
		(without the double-quotes). The _index variable is incremented to the
		character beyond the closing quote of the string.

		Strings may span multiple lines if multiline is True (which it should
		be for SQL strings, but not quoted identifiers). If a CR, LF or NULL
		character is encountered in the string, an exception is raised (calling
		methods convert this exception into an ERROR token).

		This method should be overridden in descendent classes to handle those
		SQL dialects which permit additonal escaping mechanisms (like C
		backslash escaping).
		"""
		qchar = self.char
		qcount = 1
		self._next()
		self._mark()
		while True:
			if self.char == '\0':
				raise ValueError('Unterminated string starting on line %d' % self._tokenline)
			elif self.char == '\n' and not multiline:
				raise ValueError('Illegal line break found in token')
			elif self.char == qchar:
				qcount += 1
			if self.char == qchar and self.nextchar != qchar and qcount & 1 == 0:
				break
			self._next()
		content = self.markedchars.replace(qchar*2, qchar)
		self._next()
		return content

	def _handle_apos(self):
		"""Parses single quote characters (') in the source."""
		try:
			self._add_token(STRING, self._extract_string(self.multiline_str))
		except ValueError, e:
			self._add_token(ERROR, str(e))

	def _handle_asterisk(self):
		"""Parses an asterisk character ("*") in the source."""
		self._next()
		self._add_token(OPERATOR, '*')

	def _handle_bar(self):
		"""Parses a vertical bar character ("|") in the source."""
		self._next()
		if self.char == '|':
			self._next()
			self._add_token(OPERATOR, '||')
		else:
			self._add_token(ERROR, 'Invalid operator |')

	def _handle_close_parens(self):
		"""Parses a closing parenthesis character (")") in the source."""
		self._next()
		self._add_token(OPERATOR, ')')

	def _handle_colon(self):
		"""Parses a colon character (":") in the source."""
		# XXX Need to handle a colon followed by white-space as an OPERATOR here (for compound labels)
		self._next()
		if self.char in ['"', "'"]:
			try:
				self._add_token(PARAMETER, self._extract_string(False))
			except ValueError, e:
				self._add_token(ERROR, str(e))
		else:
			self._mark()
			while self.char in self.identchars: self._next()
			self._add_token(PARAMETER, self.markedchars)

	def _handle_comma(self):
		"""Parses a comma character (",") in the source."""
		self._next()
		self._add_token(OPERATOR, ',')

	def _handle_default(self):
		"""Parses unexpected characters, returning an error."""
		self._next()
		self._add_token(ERROR, 'Unexpected character %s' % (self.char))

	def _handle_digit(self):
		"""Parses numeric digits (0..9) in the source."""
		self._mark()
		self._next()
		validchars = set('0123456789Ee.')
		while self.char in validchars:
			if self.char == '.':
				validchars -= set('.')
			elif self.char in 'Ee':
				validchars -= set('Ee.')
				if self.nextchar in '-+':
					self._next()
			self._next()
		try:
			self._add_token(NUMBER, Decimal(self.markedchars))
		except ValueError, e:
			self._add_token(ERROR, str(e))

	def _handle_equal(self):
		"""Parses equality characters ("=") in the source."""
		self._next()
		self._add_token(OPERATOR, '=')

	def _handle_greater(self):
		"""Parses greater-than characters (">") in the source."""
		self._next()
		if self.char == '=':
			self._next()
			self._add_token(OPERATOR, '>=')
		else:
			self._add_token(OPERATOR, '>')

	def _handle_ident(self):
		"""Parses unquoted identifier characters (variable) in the source."""
		self._mark()
		self._next()
		while self.char in self.identchars: self._next()
		ident = self.markedchars.upper()
		if self.char == ':':
			self._next()
			self._add_token(LABEL, ident)
		elif ident in self.keywords:
			self._add_token(KEYWORD, ident)
		else:
			self._add_token(IDENTIFIER, ident)

	def _handle_less(self):
		"""Parses less-than characters ("<") in the source."""
		self._next()
		if self.char == '=':
			self._next()
			self._add_token(OPERATOR, '<=')
		elif self.char == '>':
			self._next()
			self._add_token(OPERATOR, '<>')
		else:
			self._add_token(OPERATOR, '<')

	def _handle_minus(self):
		"""Parses minus characters ("-") in the source."""
		self._next()
		if self.sql_comments and (self.char == '-'):
			self._next()
			self._mark()
			while not self.char in '\0\n': self._next()
			content = self.markedchars
			self._next()
			self._add_token(COMMENT, content)
		else:
			self._add_token(OPERATOR, '-')

	def _handle_open_parens(self):
		"""Parses open parenthesis characters ("(") in the source."""
		self._next()
		self._add_token(OPERATOR, '(')

	def _handle_period(self):
		"""Parses full-stop characters (".") in the source."""
		if self.nextchar in '0123456789':
			# Numbers can start with . in SQL
			self._handle_digit()
		else:
			self._next()
			self._add_token(OPERATOR, '.')

	def _handle_plus(self):
		"""Parses plus characters ("+") in the source."""
		self._next()
		self._add_token(OPERATOR, '+')

	def _handle_question(self):
		"""Parses question marks ("?") in the source."""
		self._next()
		self._add_token(PARAMETER, None)

	def _handle_quote(self):
		"""Parses double quote characters (") in the source."""
		try:
			ident = self._extract_string(False)
			if self.char == ':':
				self._next()
				self._add_token(LABEL, ident)
			else:
				self._add_token(IDENTIFIER, ident)
		except ValueError, e:
			self._add_token(ERROR, str(e))

	def _handle_semicolon(self):
		"""Parses semi-colon characters (;) in the source."""
		self._next()
		self._add_token(TERMINATOR, ';')

	def _handle_slash(self):
		"""Parses forward-slash characters ("/") in the source."""
		self._next()
		if self.cpp_comments and (self.char == '/'):
			self._next()
			self._mark()
			while not self.char in '\0\n':
				self._next()
			content = self.markedchars
			self._add_token(COMMENT, content)
		elif self.c_comments and (self.char == '*'):
			self._next()
			self._mark()
			try:
				while True:
					if self.char == '\0':
						raise ValueError('Unterminated comment starting on line %d' % self._tokenline)
					elif (self.char == '*') and (self.nextchar == '/'):
						content = self.markedchars
						self._next(2)
						self._add_token(COMMENT, content)
						break
					else:
						self._next()
			except ValueError, e:
				self._add_token(ERROR, str(e))
		else:
			self._add_token(OPERATOR, '/')

	def _handle_terminator(self):
		"""Parses statement terminator characters (variable) in the source."""
		if self._source.startswith(self._terminator, self._index):
			self._next(len(self._terminator))
			self._add_token(TERMINATOR, self._terminator)
		elif self._savedhandler is not None:
			self._savedhandler()

	def _handle_space(self):
		"""Parses whitespace characters in the source."""
		while self.char in self.spacechars:
			if self.char == '\n':
				self._next()
				break
			else:
				self._next()
		self._add_token(WHITESPACE, None)


class SQL92Tokenizer(SQLTokenizerBase):
	"""ANSI SQL-92 tokenizer class."""
	pass


class SQL99Tokenizer(SQLTokenizerBase):
	"""ANSI SQL-99 tokenizer class."""

	def __init__(self):
		super(SQL99Tokenizer, self).__init__()
		self.keywords = set(sql99_keywords)
		self.identchars = set(sql99_identchars)


class SQL2003Tokenizer(SQLTokenizerBase):
	"""ANSI SQL-2003 tokenizer class."""

	def __init__(self):
		super(SQL2003Tokenizer, self).__init__()
		self.keywords = set(sql2003_keywords)
		self.identchars = set(sql2003_identchars)


class DB2ZOSTokenizer(SQLTokenizerBase):
	"""IBM DB2 UDB for z/OS tokenizer class."""

	def __init__(self):
		super(DB2ZOSTokenizer, self).__init__()
		self.keywords = set(db2zos_keywords)
		self.identchars = set(db2zos_identchars)

	def _handle_not(self):
		"""Parses characters meaning "NOT" (! and ^) in the source."""
		self._next()
		try:
			negatedop = {
				'=': '<>',
				'>': '<=',
				'<': '>=',
			}[self.char]
		except KeyError:
			self._add_token(ERROR, "Expected >, <, or =, but found %s" % (self.char))
		else:
			self._next()
			self._add_token(OPERATOR, negatedop)

	def _handle_hexstring(self):
		"""Parses a hexstring literal in the source."""
		if self.nextchar == "'":
			self._next()
			try:
				s = self._extract_string(False)
				if len(s) % 2 != 0:
					raise ValueError('Hex-string must have an even length')
				s = ''.join(chr(int(s[i:i + 2], 16)) for i in xrange(0, len(s), 2))
			except ValueError, e:
				self._add_token(ERROR, str(e))
			else:
				self._add_token(STRING, s)
		else:
			self._handle_ident()

	def _handle_unihexstring(self):
		"""Parses a unicode hexstring literal in the source."""
		if self.nextchar.upper() == 'X':
			self._next()
			if self.nextchar == "'":
				self._next()
				try:
					s = self._extract_string(False)
					if len(s) % 4 != 0:
						raise ValueError('Unicode hex-string must have a length which is a multiple of 4')
					s = ''.join(unichr(int(s[i:i + 4], 16)) for i in xrange(0, len(s), 4))
				except ValueError, e:
					self._add_token(ERROR, str(e))
				else:
					self._add_token(STRING, s)
			else:
				self._handle_ident()
		else:
			self._handle_ident()

	def _handle_unistring(self):
		"""Parses a graphic literal in the source."""
		if self.nextchar == "'":
			self._next()
			try:
				# XXX Needs testing ... what exactly is the Info Center on
				# about with these Graphic String literals (mixing DBCS in an
				# SBCS/MBCS file?!)
				s = unicode(self._extract_string(self.multiline_str))
			except ValueError, e:
				self._add_token(ERROR, str(e))
			else:
				self._add_token(STRING, s)
		elif self.char.upper() == 'G' and self.nextchar.upper() == 'X':
			self._handle_unihexstring()
		else:
			self._handle_ident()

	def _init_jump(self):
		super(DB2ZOSTokenizer, self)._init_jump()
		self._jump['!'] = self._handle_not
		self._jump['^'] = self._handle_not
		self._jump['x'] = self._handle_hexstring
		self._jump['X'] = self._handle_hexstring
		self._jump['n'] = self._handle_unistring
		self._jump['N'] = self._handle_unistring
		self._jump['g'] = self._handle_unistring
		self._jump['G'] = self._handle_unistring
		# XXX What about the hook character here ... how to encode?
		self._jump[u'\xac'] = self._handle_not


class DB2LUWTokenizer(DB2ZOSTokenizer):
	"""IBM DB2 UDB for Linux/Unix/Windows tokenizer class."""

	# XXX Need to add support for changing statement terminator on the fly
	# with --# SET TERMINATOR c (override _handle_minus() to check if last
	# token is a COMMENT, if so, set terminator property)

	def __init__(self):
		super(DB2LUWTokenizer, self).__init__()
		self.keywords = set(db2luw_keywords)
		self.identchars = set(db2luw_identchars)
		# Support for C-style /*..*/ comments add in DB2 UDB v8 FP9
		self.c_comments = True

	def _handle_ident(self):
		super(DB2LUWTokenizer, self)._handle_ident()
		# Rewrite the special values INFINITY, NAN and SNAN to their decimal
		# counterparts with token type NUMBER
		if self._tokens[-1][:2] == (IDENTIFIER, 'INFINITY'):
			self._tokens[-1] = (NUMBER, Decimal('Infinity')) + self._tokens[-1][2:]
		elif self._tokens[-1][:2] == (IDENTIFIER, 'NAN'):
			self._tokens[-1] = (NUMBER, Decimal('NaN')) + self._tokens[-1][2:]
		elif self._tokens[-1][:2] == (IDENTIFIER, 'SNAN'):
			self._tokens[-1] = (NUMBER, Decimal('sNaN')) + self._tokens[-1][2:]

	def _handle_period(self):
		"""Parses full-stop characters (".") in the source."""
		# Override the base method to handle DB2 UDB's method qualifiers (..)
		if self.nextchar == '.':
			self._add_token(OPERATOR, '..')
			self._next(2)
		else:
			super(DB2LUWTokenizer, self)._handle_period()

	def _handle_open_bracket(self):
		self._next()
		self._add_token(OPERATOR, '[')

	def _handle_close_bracket(self):
		self._next()
		self._add_token(OPERATOR, ']')

	def _handle_open_brace(self):
		self._next()
		self._add_token(OPERATOR, '{')

	def _handle_close_brace(self):
		self._next()
		self._add_token(OPERATOR, '}')

	# XXX Support for UESCAPE needed at some point. This probably can't be
	# implemented directly in the tokenizer. Instead, add a separate token type
	# for UTF-8 strings and a "pre-parse" phase to the parser which scans for
	# the new token type and a UESCAPE suffix and decodes the combination into
	# a STRING token
	utf8re = re.compile(r'\\(\\|[0-9A-Fa-f]{4}|\+[0-9A-Fa-f]{6})')
	def _handle_utf8string(self):
		"""Parses a UTF-8 string literal in the source."""
		if self.nextchar == "&":
			self._next(2)
			if not self.char == "'":
				self._add_token(ERROR, 'Expecting \'')
			else:
				def utf8sub(match):
					if match.group(1) == '\\':
						return '\\'
					elif match.group(1).startswith('+'):
						return unichr(int(match.group(1)[1:], 16))
					else:
						return unichr(int(match.group(1), 16))
				try:
					s = self._extract_string(self.multiline_str)
				except ValueError, e:
					self._add_token(ERROR, str(e))
				else:
					self._add_token(STRING, utf8re.sub(utf8sub, utf8decode(s)))
		elif self.nextchar.upper() == 'X':
			self._handle_unihexstring()
		else:
			self._handle_ident()

	def _init_jump(self):
		super(DB2LUWTokenizer, self)._init_jump()
		self._jump['['] = self._handle_open_bracket
		self._jump[']'] = self._handle_close_bracket
		self._jump['{'] = self._handle_open_brace
		self._jump['}'] = self._handle_close_brace
		self._jump['u'] = self._handle_utf8string
		self._jump['U'] = self._handle_utf8string

