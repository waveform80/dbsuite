# vim: set et sw=4 sts=4:

# Copyright 2012 Dave Hughes.
#
# This file is part of dbsuite.
#
# dbsuite is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# dbsuite is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# dbsuite.  If not, see <http://www.gnu.org/licenses/>.

"""Provides a set of base classes for HTML based output plugins.

This package defines a set of utility classes which make it easier to construct
output plugins capable of producing HTML documents (or, more precisely, a
website containing HTML documents amongst other things).
"""

from __future__ import (
    unicode_literals,
    print_function,
    absolute_import,
    division,
    )

import sys
import os
import re
import traceback
import datetime
import logging
import urlparse
import threading
from operator import attrgetter
from pkg_resources import resource_stream, resource_string

import pygraphviz as pgv

from dbsuite.main import __version__
from dbsuite.highlighters import CommentHighlighter, SQLHighlighter
from dbsuite.plugins.html.entities import HTML_ENTITIES
from dbsuite.tokenizer import TokenTypes as TT
from dbsuite.db import (
    DatabaseObject, Relation, Routine, Constraint, Database, Tablespace,
    Schema, Table, View, Alias, Index, Trigger, Function, Procedure, Datatype,
    Field, UniqueKey, PrimaryKey, ForeignKey, Check, Param
)
from dbsuite.etree import (
    fromstring, tostring, iselement, ElementFactory, flatten_html
)

# Import the xapian bindings
try:
    import xapian
except ImportError:
    # Ignore any import errors - the main plugin takes care of warning the user
    # if xapian is required but not present
    pass

# Import the fastest StringIO implementation
try:
    from cStringIO import StringIO
except ImportError:
    try:
        from StringIO import StringIO
    except ImportError:
        raise ImportError('unable to find a StringIO implementation')


# Constants for HTML versions
(
    HTML4,   # HTML 4.01
    XHTML10, # XHTML 1.0
    XHTML11, # XHTML 1.1 (modular XHTML)
) = range(3)

# Constants for HTML style
(
    STRICT,       # Strict DTD
    TRANSITIONAL, # Transitional DTD
    FRAMESET,     # Frameset DTD
) = range(3)


class HTMLElementFactory(ElementFactory):
    """Element factory class customized for HTML output."""

    def __init__(self, site):
        super(HTMLElementFactory, self).__init__()
        self._site = site

    def _format(self, content):
        """Reformats content into a human-readable string"""
        if content is None:
            # Format None as 'n/a'
            return 'n/a'
        elif isinstance(content, bool):
            # Format booleans as Yes/No
            return ['No', 'Yes'][content]
        elif isinstance(content, (int, long)):
            # Format integer number with , as a thousand separator
            s = str(content)
            for i in xrange(len(s) - 3, 0, -3):
                s = '%s,%s' % (s[:i], s[i:])
            return s
        elif isinstance(content, datetime.datetime):
            # Format timestamps as dates
            return str(content.date())
        else:
            # Use the default for everything else
            return super(HTMLElementFactory, self)._format(content)

    def script(self, *content, **attrs):
        # XXX Workaround: the script element cannot be "empty" (IE fucks up)
        if not content:
            content = (' ',)
        # If type isn't specified, default to 'text/javascript'
        if not 'type' in attrs:
            attrs['type'] = 'text/javascript'
        return self._element('script', *content, **attrs)

    def style(self, *content, **attrs):
        # Default type is 'text/css', and media is 'screen'
        if not 'type' in attrs:
            attrs['type'] = 'text/css'
        if not 'media' in attrs:
            attrs['media'] = 'screen'
        # If there's no content, and src is set, return a <link> element instead
        if not content and 'src' in attrs:
            attrs['rel'] = 'stylesheet'
            attrs['href'] = attrs['src']
            del attrs['src']
            return self._element('link', **attrs)
        else:
            return self._element('style', *content, **attrs)

    compress = re.compile(r'[ \t\r\n]+')
    def p_typed(self, content, dbobject, attrs):
        content = content % {'type': self._site.type_name(dbobject).lower()}
        content = self.compress.sub(' ', content)
        return self.p(content, **attrs)

    def p_attributes(self, dbobject, **attrs):
        # Boilerplate paragraph describing the common attributes table of a database object
        return self.p_typed("""The following table briefly lists
            general attributes of the %(type)s. Most attribute titles can be
            clicked on to gain a complete description of the attribute.""",
            dbobject, attrs)

    def p_constraint_fields(self, dbobject, **attrs):
        # Boilerplate paragraph describing the fields table of a constraint
        return self.p_typed("""The following table lists the fields constrained
            by the %(type)s. Note that the ordering of fields in the table is
            irrelevant.""",
            dbobject, attrs)

    def p_relation_fields(self, dbobject, **attrs):
        # Boilerplate paragraph describing the fields table of a relation
        s = """The following table lists the fields of the %(type)s.  The #
            column lists the 1-based position of the field in the %(type)s, the
            Type column lists the SQL data-type of the field, and Nulls
            indicates whether the field can contain the SQL NULL value."""
        if isinstance(dbobject, Alias):
            dbobject = dbobject.final_relation
        if isinstance(dbobject, Table):
            s += """ The Key Pos column will list the 1-based position of the
                field in the primary key of the table (if one exists), and the
                Cardinality column the approximate number of unique values
                stored in the field (if statistics have been gathered)."""
        return self.p_typed(s, dbobject, attrs)

    def p_overloads(self, dbobject, **attrs):
        # Boilerplate paragraph describing the overloaded versions of a routine
        return self.p_typed("""The following table lists the overloaded
            versions of this %(type)s, that is other routines with the same
            name but a different parameter list typically used to provide the
            same functionality across a range of data types.""",
            dbobject, attrs)

    def p_dependent_relations(self, dbobject, **attrs):
        # Boilerplate paragraph describing the dependent relations table of an object
        return self.p_typed("""The following table lists all relations which
            depend on this %(type)s (e.g. views which reference this %(type)s
            in their defining query).""",
            dbobject, attrs)

    def p_dependencies(self, dbobject, **attrs):
        # Boilerplate paragraph describing the dependencies of an object
        return self.p_typed("""The following table lists all relations which
            this relation depends upon (e.g. tables referenced by this %(type)s
            in its defining query).""",
            dbobject, attrs)

    def p_triggers(self, dbobject, **attrs):
        # Boilerplate paragraph describing the triggers of a relation
        return self.p_typed("""The following table lists all triggers that fire
            in response to changes (insertions, updates, and/or deletions) in
            this %(type)s.""",
            dbobject, attrs)

    def p_diagram(self, dbobject, **attrs):
        # Boilerplate paragraph describing the diagram of an object
        return self.p_typed("""The following diagram illustrates this %(type)s
            and its direct dependencies and dependents. You may click on
            objects within the diagram to visit the documentation for that
            object.""",
            dbobject, attrs)

    def p_sql_definition(self, dbobject, **attrs):
        # Boilerplate paragraph describing the SQL definition of an object
        return self.p_typed("""The SQL used to define the %(type)s is given
            below.  Note that, depending on the underlying database
            implementation, this SQL may not be accurate (in some cases the
            database does not store the original command, so the SQL is
            reconstructed from metadata), or even valid for the platform.""",
            dbobject, attrs)


class HTMLCommentHighlighter(CommentHighlighter):
    """Class which converts simple comment markup into HTML.

    This subclass of the generic comment highlighter class overrides the stub
    methods to convert the comment into HTML. The construction of the HTML
    elements is actually handled by the methods of the WebSite's tag object
    passed to the constructor as opposed to the methods in this class.
    """

    def __init__(self, site):
        super(HTMLCommentHighlighter, self).__init__()
        self.site = site

    def start_parse(self, summary):
        self._content = []

    def start_para(self):
        self._para = []

    def handle_text(self, text):
        self._para.append(text)

    def handle_strong(self, text):
        self._para.append(self.site.tag.strong(text))

    def handle_emphasize(self, text):
        self._para.append(self.site.tag.em(text))

    def handle_underline(self, text):
        self._para.append(self.site.tag.u(text))

    def handle_quote(self, text):
        self._para.append(self.site.tag.q(text))

    def find_target(self, name):
        return self.site.database.find(name)

    def handle_link(self, target):
        # If the target is something we don't generate a document for (like
        # a column), scan upwards in the hierarchy until we find a document
        # and return a link to that document with the in between objects added
        # as normal text suffixes
        self._para.append(self.site.link_to(target, parent=True))

    def end_para(self):
        self._content.append(self.site.tag.p(*self._para))

    def end_parse(self, summary):
        if summary:
            return self._para
        else:
            return self._content


class HTMLSQLHighlighter(SQLHighlighter):
    """Class which marks up SQL with HTML.

    This subclass of the generic SQL highlighter class overrides the stub
    methods to markup the SQL with HTML <span> elements. The css_classes
    attribute determines the CSS classes which are attached to the <span>
    elements.

    When operating in line_split mode, the result is a sequence of <li>
    elements containing the <span> elements.

    The construction of the HTML elements is actually handled by the methods of
    the HTMLDocument object passed to the constructor.
    """

    def __init__(self, site):
        super(HTMLSQLHighlighter, self).__init__(site.database.source, for_scripts=False)
        self.site = site
        self.css_classes = {
            TT.ERROR:      'sql-error',
            TT.COMMENT:    'sql-comment',
            TT.KEYWORD:    'sql-keyword',
            TT.IDENTIFIER: 'sql-identifier',
            TT.SCHEMA:     'sql-identifier',
            TT.RELATION:   'sql-identifier',
            TT.ROUTINE:    'sql-identifier',
            TT.LABEL:      'sql-label',
            TT.DATATYPE:   'sql-datatype',
            TT.REGISTER:   'sql-register',
            TT.NUMBER:     'sql-number',
            TT.STRING:     'sql-string',
            TT.OPERATOR:   'sql-operator',
            TT.PARAMETER:  'sql-parameter',
            TT.TERMINATOR: 'sql-terminator',
            TT.STATEMENT:  'sql-terminator',
        }

    def format_token(self, token):
        try:
            css_class = self.css_classes[(token.type, token.value)]
        except KeyError:
            css_class = self.css_classes.get(token.type, None)
        # XXX Disgusting hack because IE's too thick to handle pre-formatted
        # whitespace in anything except <pre>
        s = re.sub(' {2,}', lambda m: '\u00A0' * len(m.group()), token.source)
        if css_class is not None:
            return self.site.tag.span(s, class_=css_class)
        else:
            return s

    def format_line(self, index, line):
        return self.site.tag.li(self.format_token(token) for token in line)


class ObjectGraph(object):
    """Represents database objects within a pygraphviz AGraph.

    This is the base class for graphs used in generated web sites.
    method on all objects within the graph. Dervied plugins may override
    style() to refine or change the style, in which case they must also update
    the graph_class attribute of the site object. The overridden _get_dot()
    method caches its output (given that knowledge that html derived plugins
    always use this class in a one-shot manner). Finally, an add() method is
    introduced which can be used to add database objects to the graph easily.
    """

    def __init__(self, site, name='G'):
        super(ObjectGraph, self).__init__()
        self.graph = pgv.AGraph(
            name=name, strict=False, directed=True, rankdir='LR')
        self.dbobjects = {}
        self.graphobjects = {}
        self.selected = set()
        self.site = site

    def add_subgraph(self, dbobject, selected=False, **attr):
        """Add a cluster subgraph representing a database object to the graph.

        This method adds the specified database object to the graph as a
        cluster subgraph and attaches custom attributes to the subgraph to
        tie it to the database object it represents. Descendents should override
        this method if they wish to customize the attributes.
        """
        subgraph = self.dbobjects.get(dbobject)
        if subgraph is None:
            subgraph = self.graph.add_subgraph(
                name='cluster_%s' % dbobject.identifier,
                label=dbobject.name, **attr)
            if selected:
                self.selected.add(subgraph)
            self.graphobjects[subgraph] = dbobject
            self.dbobjects[dbobject] = subgraph
        return subgraph

    def add_node(self, dbobject, selected=False, **attr):
        """Add a node representing a database object to the graph.

        This method adds the specified database object to the graph as a node
        (or a cluster) and attaches custom attributes to the node to tie it to
        the database object it represents. Descendents should override this
        method if they wish to customize the attributes or add support for
        additional database object types.
        """
        node = self.dbobjects.get(dbobject)
        if node is None:
            subgraph = self.add_subgraph(dbobject.schema)
            subgraph.add_node(
                dbobject.identifier, label=dbobject.name, **attr)
            node = subgraph.get_node(dbobject.identifier)
            if selected:
                self.selected.add(node)
            self.graphobjects[node] = dbobject
            self.dbobjects[dbobject] = node
        return node

    def add_edge(self, from_object, to_object, key=None, dbobject=None, **attr):
        """Add an edge between two objects on the graph.

        This method adds a directed edge between from_object and to_object on
        the graph. If from_object or to_object are not present on the graph
        they will be added. If the optional key parameter is specified it can
        be used to distinguish the new edge from other parallel edges.
        Descendents should override this method if they wish to customize the
        attributes.
        """
        if dbobject and not key:
            key = dbobject.identifier
        edge = None
        from_node = self.add_node(from_object)
        to_node = self.add_node(to_object)
        self.graph.add_edge(from_node, to_node, key, **attr)
        edge = self.graph.get_edge(from_node, to_node, key=key)
        self.graphobjects[edge] = dbobject
        return edge

    def style_subgraph(self, subgraph):
        """Applies common styles to subgraphs."""
        # Overridden to add URLs to graph items representing database objects,
        # and to apply a thicker border to the selected object
        dbobject = self.graphobjects.get(subgraph)
        if dbobject:
            doc = self.site.object_document(dbobject)
            if doc:
                subgraph.graph_attr['URL'] = doc.url

    def style_node(self, node):
        """Applies common styles to graph nodes."""
        dbobject = self.graphobjects.get(node)
        if dbobject:
            doc = self.site.object_document(dbobject)
            if doc:
                node.attr['URL'] = doc.url

    def style_edge(self, edge):
        """Applies common styles to graph edges."""
        dbobject = self.graphobjects.get(edge)
        if dbobject:
            doc = self.site.object_document(dbobject)
            if doc:
                edge.attr['URL'] = doc.url

    def layout(self):
        """Generates a layout for the graph after applying styles"""
        # Ensure that we don't redo layouts if called multiple times (such as
        # when drawing a graph with a client side image map)
        if not hasattr(self.graph, 'has_layout') or not self.graph.has_layout:
            for subgraph in self.graph.subgraphs_iter():
                self.style_subgraph(subgraph)
            for node in self.graph.nodes_iter():
                self.style_node(node)
            for edge in self.graph.edges_iter():
                self.style_edge(edge)
            self.graph.layout(prog='dot')
            assert self.graph.has_layout

    def to_map(self, output):
        """Draws an XML client side image map"""
        self.layout()
        self.graph.draw(output, format='cmapx')

    def to_png(self, output):
        """Draws the graph to a PNG file"""
        self.layout()
        self.graph.draw(output, format='png')

    def to_svg(self, output):
        """Draws the graph to an SVG file"""
        self.layout()
        self.graph.draw(output, format='svg')

    def to_ps(self, output):
        """Draws the graph to a PostScript file"""
        self.layout()
        self.graph.draw(output, format='ps2')

    def to_pdf(self, output):
        """Draws the graph to a PDF file"""
        self.layout()
        self.graph.draw(output, format='pdf')


class WebSite(object):
    """Represents a collection of HTML documents (a website).

    This is the base class for a related collection of HTML documents,such as a
    website. It mainly exists to provide attributes which apply to all HTML
    documents in the collection (like author, site title, copyright, and such
    like).
    """

    def __init__(self, database, options):
        """Initializes an instance of the class."""
        super(WebSite, self).__init__()
        self.database = database
        self.urls = {}
        self.object_docs = {}
        self.object_graphs = {}
        self.first_index = None
        self.index_maps = {}
        self.index_docs = {}
        self.get_options(options)
        self.get_factories()
        self.tag = self.tag_class(self)
        self.create_documents()

    def get_options(self, options):
        """Configures the class from the dictionary of options given.

        This method is called at the start of construction. It is expected to
        set the attributes of the class according to the values in the options
        dictionary passed by the plugin (along with any default values).
        """
        self.htmlver = XHTML10
        self.htmlstyle = STRICT
        self.base_url = ''
        self.base_path = options['path']
        self.home_url = options['home_url']
        self.home_title = options['home_title']
        self.icon_url = options['icon_url']
        self.icon_type = options['icon_type']
        self.keywords = [self.database.name]
        self.author_name = options['author_name']
        self.author_email = options['author_email']
        self.top = options['top']
        self.date = datetime.datetime.today()
        self.lang, self.sublang = options['lang']
        self.copyright = options['copyright']
        self.encoding = options['encoding']
        self.search = options['search']
        self.threads = options['threads']
        self.title = options['site_title']
        self.tbspace_list = options['tbspace_list']
        self.indexes = options['indexes']
        self.diagrams = options['diagrams']
        self.type_names = {
            Alias:          'Alias',
            Check:          'Check Constraint',
            Constraint:     'Constraint',
            Database:       'Database',
            DatabaseObject: 'Object',
            Datatype:       'Data Type',
            Field:          'Field',
            ForeignKey:     'Foreign Key',
            Function:       'Function',
            Index:          'Index',
            Param:          'Parameter',
            PrimaryKey:     'Primary Key',
            Procedure:      'Procedure',
            Relation:       'Relation',
            Routine:        'Routine',
            Schema:         'Schema',
            Tablespace:     'Tablespace',
            Table:          'Table',
            Trigger:        'Trigger',
            UniqueKey:      'Unique Key',
            View:           'View',
        }
        self.default_desc = 'No description in the system catalog'

    def get_factories(self):
        """Configures the classes used by the site to generate content.

        This method is called when the WebSite class is instantiated. It sets
        the classes that the site (and associated document classes) use to
        generate content, and the document classes map itself.

        Specifically, it sets the attributes tag_class (must be a descendent of
        or compatible with HTMLElementFactory), popup_class (must be like
        HTMLPopupDocument), graph_class (must be like ObjectGraph). It also
        sets document_classes which must map database object classes to
        sequences of document classes, and index_class (must be like
        HTMLSiteIndexDocument).
        """
        self.tag_class = HTMLElementFactory
        self.popup_class = HTMLPopupDocument
        self.graph_class = ObjectGraph
        self.document_classes = {}
        self.index_class = HTMLSiteIndexDocument

    def create_documents(self, phase=0):
        """Creates the documents associated with the site.

        This method constructs all the documents associated with the site. It
        is called multiple times as the last phase of the construction of
        WebSite. On each call, the phase parameter is incremented by one. The
        reason for the multiple calls is that many documents depend on other
        documents being present prior to their construction (e.g. documents
        which depend on fixed stylesheets, or scripts). Hence documents with
        no dependencies should be constructed in phase 0, documents which depend
        on these in phase 1, and so on.

        Although rather unorthodox, this system permits descendents to
        intermingle creation of their documents with the base class' creation
        order without spawning myriad oddly named create_something_documents
        methods.

        This method is called continually with an incrementing phase parameter
        until it returns False. Hence, descendents should ensure they return
        the result of the superclass' call or'ed with their own result.
        """
        self.create_static_documents()
        self.create_popup_documents()
        self.create_index_levels()
        self.create_object_documents()
        if self.index_docs:
            self.create_index_links()

    def create_static_documents(self):
        """Creates the static documents required by the site."""
        # Build the static documents (basically just file copies with optional
        # transcoding to the site's encoding)
        self.sql_style = SQLStyle(self)
        self.jquery_script = JQueryScript(self)
        self.tablesorter_script = TablesorterScript(self)
        self.thickbox_style = ThickboxStyle(self)
        self.thickbox_script = ThickboxScript(self)
        ThickboxImage(self)

    def create_popup_documents(self):
        """Creates the popup documents required by the site."""
        # Build the static popup documents
        popups = fromstring(resource_string(__name__, 'popups.xml'))
        for popup in popups:
            self.popup_class(site=self, body=list(popup), **popup.attrib)

    def create_object_documents(self):
        """Creates the documents for database objects in the site."""
        # Build the object and index documents
        for dbobject in self.database:
            self.add_object(dbobject)
        for cls in self.index_maps:
            for letter in self.index_maps[cls]:
                self.index_class(self, cls, letter)

    def create_index_levels(self):
        """Creates the index documents required by the site."""
        # If indexes are requested, build the sorted object lists now (and set
        # up the first level of the index_docs mapping)
        if self.indexes:
            for cls in self.indexes:
                self.index_maps[cls] = {}
                self.index_docs[cls] = {}
            for dbobject in self.database:
                self.index_object(dbobject, self.indexes)

    def create_index_links(self):
        """Utility method for linking letters of indexes together.

        This method is called during write() to generate the first, prior,
        next, last, and parent links of the index documents. Normally, this
        sort of thing would be done in the generate() method of the document in
        question. However, it's much more efficient to do this at the site
        level for the index documents as we can sort the list of documents by
        letter once, and apply the links from the result.

        In this method, we also generate a bunch of "fake" documents
        representing each index. The HTMLExternalDocument class is used for
        this, and each "fake" document actually points to the document for the
        first letter of the index. These documents are used to provide another
        level of structure to the document hierarchy, which groups together
        each index letter document, e.g.:

        Database Document
        +- Table Index (fake)
        |  +- A
        |  +- B
        |  +- C
        |  +- D
        |  +- ...
        +- View Index (fake)
           +- A
           +- B
           +- ...

        Override this in descendents if the index_docs structure is changed or
        enhanced.
        """
        # Sort the list of database classes by name and filter out those which
        # have no index content
        dbclasses = [
            dbclass for dbclass in sorted(self.index_docs.iterkeys(),
                key=lambda dbclass: self.type_name(dbclass))
            if self.index_docs[dbclass]
        ]
        # Create "fake" documents to represent each index. Note that the URL
        # constructed here is ultimately discarded, but must still be unique
        # (see below)
        dbclass_docs = [
            HTMLExternalDocument(self,
                'indexof_%s.html' % dbclass.config_names[0],
                '%s Index' % self.type_name(dbclass)
            )
            for dbclass in dbclasses
        ]
        self.first_index = dbclass_docs[0]
        dbclass_parent = self.object_document(self.database)
        dbclass_prior = None
        for (dbclass, dbclass_doc) in zip(dbclasses, dbclass_docs):
            letter_docs = sorted(self.index_docs[dbclass].itervalues(), key=attrgetter('letter'))
            if letter_docs:
                # Replace the URL of the class document with the URL of the
                # first letter of the index. We can't do this at construction
                # time or the fake document will supplant the real document
                # (for the first letter) in the site's structures.
                dbclass_doc.url = letter_docs[0].url
                dbclass_doc.first = dbclass_docs[0]
                dbclass_doc.last = dbclass_docs[-1]
                dbclass_doc.parent = dbclass_parent
                dbclass_doc.prior = dbclass_prior
                dbclass_prior = dbclass_doc
                letter_prior = None
                for letter_doc in letter_docs:
                    letter_doc.first = letter_docs[0]
                    letter_doc.last = letter_docs[-1]
                    letter_doc.parent = dbclass_doc
                    letter_doc.prior = letter_prior
                    letter_prior = letter_doc

    def add_object(self, dbobject):
        """Adds documents for a specific database object.

        This a utility method called for each object in the database hierarchy.
        The default implementation here uses the mapping of database object
        classes to sets of document classes (document_classes) to generate
        document(s) for the specific database object. Descendents may choose to
        override this if they have different methods of determining what
        documents to create (if any).
        """
        def find_doc_classes(cls):
            # Look for a perfect class match, and if not found, search along
            # each base class' hierarchy for matches
            try:
                return self.document_classes[cls]
            except KeyError:
                for base in cls.__bases__:
                    try:
                        return find_doc_classes(base)
                    except ValueError:
                        continue
                raise ValueError('Unable to find a mapping for %s' % cls)
        try:
            doc_classes = find_doc_classes(type(dbobject))
        except ValueError:
            pass
        else:
            for doc_class in doc_classes:
                doc_class(self, dbobject)

    def index_object(self, dbobject, dbclasses):
        """Adds a database object to the relevant index lists.

        This is a utility method called for each object in the database
        hierarchy. If the object is an instance of any class in dbclasses, it
        is added to an index list (index lists are keyed by database class and
        initial letter). Note that the lists are not sorted here (or even in
        the caller) - it is up to index documents to sort these lists (which
        allows for multiple index documents to reference the same index list
        and sort it in different ways).
        """
        for cls in dbclasses:
            if isinstance(dbobject, cls):
                letter = dbobject.name[:1]
                if letter in self.index_maps[cls]:
                    self.index_maps[cls][letter].append(dbobject)
                else:
                    self.index_maps[cls][letter] = [dbobject]

    def add_document(self, document):
        """Adds a document to the website.

        This method adds a document to the website, and updates several data
        structures which track the associations between database objects and
        documents / graphs. The base implementation here permits a database
        object to be associated with a single document and a single graph.
        Descendents may override this method (and the object_document() and
        object_graph() methods) if more complex associations are desired (e.g.
        framed and non-framed versions of documents).
        """
        logging.debug('Adding document %s' % document.url)
        self.urls[document.url] = document
        self.urls[document.absolute_url] = document
        if isinstance(document, HTMLObjectDocument):
            self.object_docs[document.dbobject] = document
        elif isinstance(document, GraphObjectDocument):
            self.object_graphs[document.dbobject] = document
        elif isinstance(document, HTMLSiteIndexDocument):
            self.index_docs[document.dbclass][document.letter] = document

    def url_document(self, url):
        """Returns the WebSiteDocument associated with a given URL.

        This method returns the document with the specified URL (or None if no
        such URL exists in the site).
        """
        return self.urls.get(url)

    def index_document(self, dbclass, letter=None, *args, **kwargs):
        """Returns the HTMLDocument which indexes a particular database class.

        This methods returns a single HTMLDocument which contains an index for
        the specified database class (e.g. tables), if one exists (if one does
        not exist, the result is None).

        If the optional letter parameter is provided, and an index for the
        specific letter of the database class can be found, it will be
        returned. Otherwise, the first index (in alphabetical terms) for the
        class will be returned.

        The args and kwargs parameters capture any extra criteria that should
        be used to select between documents in the case that an index is
        represented by multiple documents (e.g. framed and unframed versions).
        """
        assert issubclass(dbclass, DatabaseObject)
        if letter:
            try:
                return self.index_docs[dbclass][letter]
            except KeyError:
                return None
        else:
            docs = self.index_docs.get(dbclass)
            if docs:
                return docs[sorted(docs.keys())[0]]
            else:
                return None

    def object_document(self, dbobject, *args, **kwargs):
        """Returns the HTMLDocument associated with a database object.

        This method returns a single HTMLDocument which is associated with the
        specified database object (dbobject). If the specified object has no
        associated HTMLDocument object, the method returns None.

        Descendents may override this method to alter the way database objects
        are associated with GraphDocuments.

        The args and kwargs parameters capture any extra criteria that should
        be used to select between documents in the case that a database object
        is represented by multiple documents (e.g. framed and unframed
        versions).  They correspond to the args and kwargs parameters of the
        link_to() method.
        """
        return self.object_docs.get(dbobject)

    def object_graph(self, dbobject, *args, **kwargs):
        """Returns the GraphDocument associated with a database object.

        This method returns a single GraphDocument which is associated with the
        specified database object (dbobject). If the specified objcet has no
        associated GraphDocument object, the method returns None.

        Descendents may override this method to alter the way database objects
        are associated with GraphDocuments.

        The args and kwargs parameters capture any extra criteria that should
        be used to select between graphs in the case that a database object is
        represented by multiple graphs (e.g. relational integrity versus
        functional dependencies).  They correspond to the args and kwargs
        parameters of the img_of() method.
        """
        return self.object_graphs.get(dbobject)

    def type_name(self, dbobject):
        """Returns the string naming the object's type.

        This method returns a string describing the object's type, looked up in
        the type_names dictionary. If an exact match can be found, it is
        returned, otherwise a subclass match is sufficient.
        """
        def class_type_name(cls):
            try:
                return self.type_names[cls]
            except KeyError:
                for base in cls.__bases__:
                    try:
                        return class_type_name(base)
                    except KeyError:
                        continue
                raise ValueError('Cannot find name of %s' % cls)
        if isinstance(dbobject, type):
            return class_type_name(dbobject)
        else:
            return class_type_name(type(dbobject))

    def link_to(self, dbobject, parent=False, *args, **kwargs):
        """Returns a link to a document representing the specified database object.

        Given a database object, this method returns the Element(s) required to
        link to an HTMLDocument representing that object. The link will include
        the object's fully qualified name.

        If the specified object is not associated with any HTMLDocument, the
        parent parameter determines the result. If parent is False (the
        default), the method returns the text that the link would have
        contained (according to the typename and qualifiedname parameters).
        Otherwise, the method searches the object's parents for an associated
        document, returning a link to the first documented parent found.

        The args and kwargs parameters permit additional arguments to be
        relayed to the object_document() method in case the site implements
        multiple documents per object (e.g. framed and non-framed versions).
        """
        doc = self.object_document(dbobject, *args, **kwargs)
        if doc:
            return self.tag.a(dbobject.qualified_name, href=doc.url, title=doc.title)
        elif parent:
            suffixes = []
            target = dbobject
            while doc is None:
                suffixes.insert(0, target.name)
                target = target.parent
                doc = self.object_document(target, *args, **kwargs)
                if isinstance(target, Database):
                    target = None
                    break
            return [
                self.link_to(target, False, *args, **kwargs),
                ''.join('.' + s for s in suffixes),
            ]
        else:
            return dbobject.qualified_name

    def img_of(self, dbobject, *args, **kwargs):
        """Returns a link to a graph representing the specified database object.

        Given a database object, this method returns the Element(s) required to
        link to a GraphDocument representing that object.

        The args and kwargs parameters permit additional arguments to be
        relayed to the object_document() method in case the site implements
        multiple graphs per object.

        If the specified object is not associated with any GraphDocument, the
        method returns some text indicating that no graph is available.
        """
        graph = self.object_graph(dbobject, *args, **kwargs)
        if graph is None:
            return self.tag.p('Graph for %s is not available' % dbobject.qualified_name)
        else:
            return graph.link()

    def index_of(self, dbclass, letter=None, *args, **kwargs):
        """Returns a link to an index of objects of the specified class.

        Given a database class (Table, Relation, etc.), this method returns
        the Element(s) required to link to the alphabetical index of objects
        of that class.

        If the letter parameter is ommitted, the link will be to the first
        letter of the index. The args and kwargs parameters permit additional
        arguments to be relayed to the index_document() method in case the site
        implements multiple indexes per class.

        If the specified class does not have an associated index, the method
        returns some text indicating that no index is available.
        """
        assert issubclass(dbclass, DatabaseObject)
        doc = self.index_document(dbclass, letter, *args, **kwargs)
        if doc is None:
            return self.tag.p('%s index is not available' % self.type_name(dbclass))
        elif letter is None:
            return doc.link()
        else:
            return self.tag.a(letter, href=doc.url, title=doc.title)

    def write(self):
        """Writes all documents in the site to disk."""
        logging.info('Writing output to "%s"' % self.base_path)
        if self.threads == 1:
            if self.diagrams:
                logging.info('Writing documents and graphs')
            else:
                logging.info('Writing documents')
            self.write_single(self.urls.itervalues())
        else:
            # Writing documents with multiple threads is split into two phases:
            # writing graphs, and writing non-graphs. This avoids a race
            # condition; in plugins which automatically resize large diagrams,
            # writing an HTMLDocument that references a GraphDocument can cause
            # the GraphDocument to be written in order to determine its size.
            # If another thread starts writing the same GraphDocument
            # simultaneously two threads wind up trying to write to the same
            # file
            if self.diagrams:
                logging.info('Writing graphs')
                self.write_multi(
                    doc for doc in self.urls.itervalues()
                    if isinstance(doc, GraphDocument)
                )
            logging.info('Writing documents')
            self.write_multi(
                doc for doc in self.urls.itervalues()
                if not isinstance(doc, GraphDocument)
            )
        if self.search:
            # Write all full-text-search documents to a new xapian database
            # in a single transaction
            logging.info('Writing search database')
            db = xapian.WritableDatabase(os.path.join(self.base_path, 'search'),
                xapian.DB_CREATE_OR_OVERWRITE)
            db.begin_transaction()
            try:
                for doc in self.urls.itervalues():
                    if isinstance(doc, HTMLDocument) and doc.ftsdoc:
                        db.add_document(doc.ftsdoc)
                db.commit_transaction()
            except:
                db.cancel_transaction()
                raise

    def start_progress(self, total):
        self._progress_start = datetime.datetime.now()
        self._progress_total = total
        self._progress_last = self._progress_start
        logging.info('%d documents remaining' % total)

    def write_progress(self, remaining):
        if (datetime.datetime.now() - self._progress_last).seconds >= 60:
            elapsed = datetime.datetime.now() - self._progress_start
            rate = (self._progress_total - remaining) / float((elapsed.days * 86400) + elapsed.seconds)
            eta = datetime.timedelta(seconds=int(remaining / rate))
            logging.info('%d documents remaining, ETA %s @ %.2f docs/sec' % (remaining, eta, rate))
            self._progress_last = datetime.datetime.now()

    def finish_progress(self):
        elapsed = datetime.datetime.now() - self._progress_start
        # Get rid of microseconds from elapsed for display purposes
        elapsed = datetime.timedelta(days=elapsed.days, seconds=elapsed.seconds)
        try:
            rate = self._progress_total / float((elapsed.days * 86400) + elapsed.seconds)
        except ZeroDivisionError:
            rate = 0
        logging.info('%d documents written in %s @ %.2f docs/sec' % (self._progress_total, elapsed, rate))
        del self._progress_start, self._progress_total, self._progress_last

    def write_single(self, docs):
        """Single-threaded document writer method."""
        logging.debug('Single-threaded writer')
        docs = set(docs)
        self.start_progress(len(docs))
        while docs:
            self.write_progress(len(docs))
            doc = docs.pop()
            try:
                doc.write()
            except Exception, e:
                # XXX Temporary hack to trace down errors
                logging.error('While writing %s:' % doc.filename)
                for line in traceback.format_exception(*sys.exc_info()):
                    for s in line.rstrip().split('\n'):
                        logging.error(s)
        self.finish_progress()

    def write_multi(self, docs):
        """Multi-threaded document writer method.

        This method sets up several parallel threads to handle writing
        documents. The documents to be written are stored in a set (to ensure
        that if documents are registered multiple times they are still only
        written once). The method terminates when all documents have been
        written. The number of parallel threads is controlled by the "threads"
        configuration value.
        """
        logging.debug('Multi-threaded writer with %d threads' % self.threads)
        self._documents_set = set(docs)
        self.start_progress(len(self._documents_set))
        # Create and start all the writing threads
        threads = [
            (i, threading.Thread(target=self.__thread_write, args=()))
            for i in range(self.threads)
        ]
        for (i, thread) in threads:
            logging.info('Starting writer thread #%d' % i)
            thread.start()
        # Join (wait on termination of) all writing threads
        while threads:
            (i, thread) = threads.pop()
            while thread.isAlive():
                self.write_progress(len(self._documents_set))
                thread.join(10.0)
            logging.info('Writer thread #%d finished' % i)
        self.finish_progress()

    def __thread_write(self):
        """Sub-routine for writing documents.

        This method runs in a separate thread and simply pops a document to
        be written from the internal stack and writes it. The thread terminates
        when no more documents remain in the stack.
        """
        while self._documents_set:
            doc = self._documents_set.pop()
            try:
                doc.write()
            except Exception, e:
                # XXX Temporary hack to trace down errors
                logging.error('While writing %s:' % doc.filename)
                for line in traceback.format_exception(*sys.exc_info()):
                    for s in line.rstrip().split('\n'):
                        logging.error(s)


class WebSiteDocument(object):
    """Represents a document in a website (e.g. HTML, CSS, image, etc.)"""

    def __init__(self, site, url):
        """Initializes an instance of the class."""
        super(WebSiteDocument, self).__init__()
        self.mimetype = 'application/octet-stream'
        self.site = site
        self.url = url
        self.absolute_url = urlparse.urljoin(self.site.base_url, url)
        parts = [self.site.base_path] + self.url.split('/')
        self.filename = os.path.join(*parts)
        self.tag = self.site.tag
        self.site.add_document(self)

    def generate(self):
        """Generates the document's content.

        Derived classes should override this method to generate the content of
        the document, returning it in a format suitable for passing to the
        serialize method.
        """
        return ''

    def serialize(self, content):
        """Converts content into a byte string for writing to disk.

        Derived classes should override this method if they need to serialize
        types other than unicode (which is the only type this base
        implementation handles).
        """
        if isinstance(content, basestring):
            if isinstance(content, unicode):
                return content.encode(self.site.encoding)
            else:
                return content
        elif hasattr(content, 'read'):
            return content.read()
        else:
            raise ValueError('unable to serialize content of type %s' % type(content))

    def write(self):
        """Writes this document to a file in the site's path.

        Derived classes generally shouldn't need to override this method. The
        base implementation here uses generate() to create the document content
        and serialize() to convert it to a byte string. Derived classes should
        consider overriding those methods instead.
        """
        logging.debug('Writing %s' % self.filename)
        with open(self.filename, 'wb') as f:
            f.write(self.serialize(self.generate()))

    def link(self, *args, **kwargs):
        """Returns the Element(s) required to link to the document.

        Derived classes should override this method to produce the Element(s)
        required to link to this document. In the case of an HTML document,
        this is likely to be an <a>nchor, while a graphic might produce an
        <img> element, and a stylesheet a <link> element. The default
        implementation here simply returns the url as a link.

        The args and kwargs parameters capture additional information for the
        generation of the link. For example, in the case of a stylesheet a
        media parameter might be included.
        """
        return self.tag.a(self.url, href=self.url)


class StaticDocument(WebSiteDocument):
    """Represents a web site document with statically defined content.

    This is the base class for documents sourced from a package resource. The
    source parameter of the constructor specifies the name of the resource.  If
    the encoding parameter is None, the resource is assumed to be binary (e.g.
    an image) and no transcoding will occur.  Otherwise, the specified encoding
    will be used to decode the resource to unicode, before re-encoding it with
    the site's configured encoding.
    """

    def __init__(self, site, url, content, encoding=None):
        if url is None:
            url = os.path.basename(source)
        super(StaticDocument, self).__init__(site, url)
        self.content = content
        self.encoding = encoding

    def generate(self):
        if self.encoding:
            if hasattr(self.content, 'read'):
                self.content = self.content.read()
            return self.content.decode(self.encoding)
        else:
            return self.content


class ImageDocument(StaticDocument):
    """Represents a static image.

    This is the base class for static images. It provides no methods for
    constructing or editing images; simply specify the source file as the
    source parameter to the constructor, or replace the generate method to
    return the image to write to the target file.
    """

    def __init__(self, site, url, content, alt=None):
        super(ImageDocument, self).__init__(site, url, content, encoding=None)
        self.mimetype = 'image/png'
        self.alt = alt

    def link(self, *args, **kwargs):
        # Overridden to return an <img> element
        return self.tag.img(src=self.url, alt=self.alt)


class StyleDocument(StaticDocument):
    """Represents a simple static CSS document.

    This is the base class for CSS stylesheets. It provides no methods for
    constructing or editing CSS; simply specify the source file as the source
    parameter to the constructor, or replace the generate method to return the
    CSS to write to the target file.
    """

    def __init__(self, site, url, content, encoding='UTF-8', media='all'):
        super(StyleDocument, self).__init__(site, url, content, encoding)
        self.mimetype = 'text/css'
        self.media = media

    def link(self, *args, **kwargs):
        # Overridden to return a <link> to the stylesheet (the tag
        # ElementFactory takes care of converting <style> into <link> when
        # there's no content, and src is specified)
        return self.tag.style(src=self.url, media=self.media)


class ScriptDocument(StaticDocument):
    """Represents a simple JavaScript document.

    This is the base class for JavaScript libraries. It provides no methods for
    constructing or editing JavaScript; simply specify the source file as the
    source parameter to the constructor, or replace the generate method to
    return the CSS to write to the target file.
    """

    def __init__(self, site, url, content, encoding='UTF-8'):
        super(ScriptDocument, self).__init__(site, url, content, encoding)
        self.mimetype = 'text/javascript'

    def link(self, *args, **kwargs):
        # Overridden to return a <script> element
        return self.tag.script(src=self.url)


class XMLDocument(WebSiteDocument):
    """Represents a simple XML document.

    This is the base class for XML documents. It provides no methods for
    constructing or editing XML, it simply overrides the serialize() method to
    handle the case where the generate() method returns an ElementTree, and
    adds the public_id and system_id attributes for construction of the
    (optional) DOCTYPE declaration.
    """

    def __init__(self, site, url):
        super(XMLDocument, self).__init__(site, url)
        self.mimetype = 'text/xml'
        self.public_id = None
        self.system_id = None
        self.entities = None

    def serialize(self, content):
        if iselement(content):
            # Construct the XML PI, and add the optional DOCTYPE (if we've got
            # public and system IDs)
            result = ['<?xml version="1.0" encoding="%s"?>' % self.site.encoding]
            if self.public_id and self.system_id:
                result.append('<!DOCTYPE %s PUBLIC "%s" "%s">' % (content.tag, self.public_id, self.system_id))
            content = unicode(tostring(content))
            if self.entities:
                # Dirty manual hack to convert non-XML entities (to support
                # things like HTML)
                def subfunc(match):
                    if ord(match.group()) in self.entities:
                        return '&%s;' % self.entities[ord(match.group())]
                    else:
                        return match.group()
                entities_re = re.compile('[%s-%s]' % (
                    unichr(min(self.entities.iterkeys())),
                    unichr(max(self.entities.iterkeys()))
                ))
                content = entities_re.sub(subfunc, content)
            # Glue everything together as a unicode string and leave it to the
            # parent to handle the transcoding...
            result.append(content)
            content = '\n'.join(result)
        return super(XMLDocument, self).serialize(content)


class HTMLDocument(XMLDocument):
    """Represents a simple HTML document.

    This is the base class for HTML documents. It provides several utility
    methods for constructing HTML elements, formatting content, and writing out
    the final HTML document. Construction of HTML elements is handled by the
    ElementTree API.
    """

    def __init__(self, site, url):
        super(HTMLDocument, self).__init__(site, url)
        self.mimetype = 'text/html'
        self.ftsdoc = None
        self.title = ''
        self.description = ''
        self.keywords = []
        self.robots_index = True
        self.robots_follow = True
        self.comment_highlighter = HTMLCommentHighlighter(self.site)
        self.sql_highlighter = HTMLSQLHighlighter(self.site)
        try:
            (self.public_id, self.system_id) = {
                (HTML4, STRICT):         ('-//W3C//DTD HTML 4.01//EN',              'http://www.w3.org/TR/html4/strict.dtd'),
                (HTML4, TRANSITIONAL):   ('-//W3C//DTD HTML 4.01 Transitional//EN', 'http://www.w3.org/TR/html4/loose.dtd'),
                (HTML4, FRAMESET):       ('-//W3C//DTD HTML 4.01 Frameset//EN',     'http://www.w3.org/TR/html4/frameset.dtd'),
                (XHTML10, STRICT):       ('-//W3C//DTD XHTML 1.0 Strict//EN',       'http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd'),
                (XHTML10, TRANSITIONAL): ('-//W3C//DTD XHTML 1.0 Transitional//EN', 'http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd'),
                (XHTML10, FRAMESET):     ('-//W3C//DTD XHTML 1.0 Frameset//EN',     'http://www.w3.org/TR/xhtml1/DTD/xhtml1-frameset.dtd'),
                (XHTML11, STRICT):       ('-//W3C//DTD XHTML 1.1//EN',              'xhtml11-flat.dtd'),
            }[(self.site.htmlver, self.site.htmlstyle)]
        except KeyError:
            raise KeyError('Invalid HTML version and style (XHTML11 only supports the STRICT style)')
        self.entities = HTML_ENTITIES
        self._first = None
        self._prior = None
        self._next = None
        self._last = None
        self._parent = None

    def _get_first(self):
        return self._first
    def _set_first(self, value):
        assert (value is None) or isinstance(value, HTMLDocument)
        self._first = value

    def _get_prior(self):
        return self._prior
    def _set_prior(self, value):
        assert (value is None) or isinstance(value, HTMLDocument)
        assert not value is self
        if self._prior:
            self._prior._next = None
        self._prior = value
        if value:
            value._next = self

    def _get_next(self):
        return self._next
    def _set_next(self, value):
        assert (value is None) or isinstance(value, HTMLDocument)
        assert not value is self
        if self._next:
            self._next._prior =None
        self._next = value
        if value:
            value._prior = self

    def _get_last(self):
        return self._last
    def _set_last(self, value):
        assert (value is None) or isinstance(value, HTMLDocument)
        self._last = value

    def _get_parent(self):
        return self._parent
    def _set_parent(self, value):
        assert (value is None) or isinstance(value, HTMLDocument)
        assert not value is self
        self._parent = value

    def _get_level(self):
        result = 0
        item = self
        while item.parent:
            result += 1
            item = item.parent
        return result

    first = property(lambda self: self._get_first(), lambda self, value: self._set_first(value))
    prior = property(lambda self: self._get_prior(), lambda self, value: self._set_prior(value))
    next = property(lambda self: self._get_next(), lambda self, value: self._set_next(value))
    last = property(lambda self: self._get_last(), lambda self, value: self._set_last(value))
    parent = property(lambda self: self._get_parent(), lambda self, value: self._set_parent(value))
    level = property(_get_level)

    def serialize(self, content):
        if iselement(content):
            assert content.tag == 'html'
            # If full-text-searching is enabled, set up a Xapian indexer and
            # stemmer and fill out the ftsdoc. The site class handles writing
            # all the ftsdoc's to the xapian database once all writing is
            # finished
            if self.site.search:
                logging.debug('Indexing %s' % self.filename)
                indexer = xapian.TermGenerator()
                # XXX Seems to be a bug in xapian 1.0.2 which causes a segfault
                # with this enabled
                #indexer.set_flags(xapian.TermGenerator.FLAG_SPELLING)
                indexer.set_stemmer(xapian.Stem(self.site.lang))
                self.ftsdoc = xapian.Document()
                self.ftsdoc.set_data('\n'.join([
                    self.url,
                    self.title or self.url,
                    self.description or self.title or self.url,
                ]))
                indexer.set_document(self.ftsdoc)
                indexer.index_text(self.flatten(content))
        return super(HTMLDocument, self).serialize(content)

    def flatten(self, content):
        """Converts the document into pure text for full-text indexing."""
        # This base implementation simply flattens the content of the HTML body
        # node. Descendents may override this to refine the output (e.g. to exclude
        # common headings and other items essentially useless for searching)
        return flatten_html(content.find('body'))

    def generate(self):
        """Called by write() to generate the document as an ElementTree."""
        # Generate and return the document
        doc = self.tag.html(self.generate_head(), self.generate_body())
        if self.site.htmlver >= XHTML10:
            doc.attrib['xmlns'] = 'http://www.w3.org/1999/xhtml'
        return doc

    def generate_head(self):
        """Called by generate() to generate the document <head> element."""
        # Override this in descendent classes to include additional content
        # Add some standard <meta> elements (encoding, keywords, author, robots
        # info, Dublin Core stuff, etc.)
        tag = self.tag
        head = tag.head(
            tag.meta(name='Robots', content=','.join((
                '%sindex'  % ('no', '')[bool(self.robots_index)],
                '%sfollow' % ('no', '')[bool(self.robots_follow)],
            ))),
            tag.meta(name='DC.Date', content=self.site.date, scheme='iso8601'),
            tag.meta(name='DC.Language', content='%s-%s' % (self.site.lang, self.site.sublang), scheme='rfc1766')
        )
        head.append(tag.meta(name='Generator', content='db2makedoc %s' % __version__))
        if self.site.copyright is not None:
            head.append(tag.meta(name='DC.Rights', content=self.site.copyright))
        if self.description is not None:
            head.append(tag.meta(name='Description', content=self.description))
        if len(self.keywords) > 0:
            head.append(tag.meta(name='Keywords', content=', '.join(self.keywords)))
        if self.site.author_email is not None:
            head.append(tag.meta(name='Owner', content=self.site.author_email))
            head.append(tag.meta(name='Feedback', content=self.site.author_email))
            head.append(tag.link(rel='author', href='mailto:%s' % self.site.author_email, title=self.site.author_name))
        # Add some navigation <link> elements
        head.append(tag.link(rel='home', href=self.site.home_url))
        if self.first:
            head.append(tag.link(rel='first', href=self.first.url))
        if self.prior:
            head.append(tag.link(rel='prev', href=self.prior.url))
        if self.next:
            head.append(tag.link(rel='next', href=self.next.url))
        if self.last:
            head.append(tag.link(rel='last', href=self.last.url))
        if self.parent:
            head.append(tag.link(rel='up', href=self.parent.url))
        # Add <link> elements for the favicon
        if self.site.icon_url:
            head.append(tag.link(rel='icon', href=self.site.icon_url, type=self.site.icon_type))
            head.append(tag.link(rel='shortcut icon', href=self.site.icon_url, type=self.site.icon_type))
        # Add the title
        if self.title is not None:
            head.append(tag.title('%s - %s' % (self.site.title, self.title)))
        # Add the JQuery, Tablesorter and Thickbox links (all used to support
        # markup generated by HTMLElementFactory)
        head.append(self.site.jquery_script.link())
        head.append(self.site.tablesorter_script.link())
        head.append(self.site.thickbox_style.link())
        head.append(self.site.thickbox_script.link())
        return head

    def generate_body(self):
        """Called by generate() to generate the document <body> element."""
        return self.tag.body()

    def format_comment(self, comment, summary=False):
        return self.comment_highlighter.parse(comment or self.site.default_desc, summary)

    def format_sql(self, sql, terminator=';', number_lines=False, id=None):
        tokens = self.sql_highlighter.parse(sql, terminator, line_split=number_lines)
        if number_lines:
            return self.tag.ol(tokens, class_='sql', id=id)
        else:
            return self.tag.pre(tokens, class_='sql', id=id)

    def format_prototype(self, sql):
        return self.tag.code(self.sql_highlighter.parse_prototype(sql), class_='sql')

    def link(self, *args, **kwargs):
        return self.tag.a(self.title, href=self.url, title=self.title)


class HTMLPopupDocument(HTMLDocument):
    """Document class representing a popup help window."""

    def __init__(self, site, url, title, body, width=400, height=300):
        """Initializes an instance of the class."""
        super(HTMLPopupDocument, self).__init__(site, url)
        self.title = title
        self.body = body
        self.width = int(width)
        self.height = int(height)

    def generate_body(self):
        tag = self.tag
        return tag.body(
            tag.div(
                tag.h3(self.title),
                self.body,
                class_='popup'
            )
        )

    def link(self):
        # Modify the link to use Thickbox
        return self.tag.a(self.title, class_='thickbox',
            href='%s?TB_iframe=true&width=%d&height=%d' % (self.url, self.width, self.height))


class HTMLExternalDocument(HTMLDocument):
    """Document class representing an external document.

    This class is used to represent HTML documents which are not generated by
    db2makedoc (whether on the local web server or elsewhere). The write()
    method of this class is overridden to do nothing. Instances of this class
    primarily serve as the target of other document's links.
    """

    def __init__(self, site, url, title):
        super(HTMLExternalDocument, self).__init__(site, url)
        self.title = title

    def write(self):
        # Overridden to do nothing
        pass


class HTMLSiteIndexDocument(HTMLDocument):
    """Document class representing an alphabetical index of objects."""

    def __init__(self, site, dbclass, letter):
        assert dbclass in site.index_maps
        assert letter in site.index_maps[dbclass]
        # Set dbclass and letter before calling the inherited method so that
        # site.add_document knows what to do with us
        self.dbclass = dbclass
        self.letter = letter
        # If the letter isn't a simple ASCII alphanumeric character, use the
        # hex value of the character in the URL (which becomes the filename),
        # in case the character is either illegal for the underlying FS (e.g.
        # backslash on Windows), or the FS doesn't support Unicode (e.g. some
        # older UNIX FSs)
        if letter == '':
            url = 'indexof_%s_empty.html' % dbclass.config_names[0]
        elif re.match('[a-zA-Z0-9]', letter):
            url = 'indexof_%s_%s.html' % (dbclass.config_names[0], letter)
        else:
            url = 'indexof_%s_%s.html' % (dbclass.config_names[0], hex(ord(letter)))
        super(HTMLSiteIndexDocument, self).__init__(site, url)
        self.title = '%s Index' % self.site.type_name(dbclass)
        self.description = self.title
        self.search = False
        self.items = site.index_maps[dbclass][letter]

    def generate_body(self):
        body = super(HTMLSiteIndexDocument, self).generate_body()
        tag = self.tag
        # Sort the list of items in the index, and build the content. Note that
        # self.items is actually reference to a site level object and therefore
        # must be considered read-only, hence why the list is not sorted
        # in-place here
        index = sorted(self.items, key=lambda item: '%s %s' % (item.name, item.qualified_name))
        index = sorted(dict(
            (item1.name, [item2 for item2 in index if item1.name == item2.name])
            for item1 in index
        ).iteritems(), key=lambda (name, _): name)
        body.append(
            tag.dl(
                ((
                    tag.dt(name),
                    tag.dd(
                        tag.dl(
                            (
                                tag.dt(self.site.type_name(item), ' ', self.site.link_to(item, parent=True)),
                                tag.dd(self.format_comment(item.description, summary=True))
                            ) for item in items
                        )
                    )
                ) for (name, items) in index),
                id='index-list'
            )
        )
        return body


class HTMLObjectDocument(HTMLDocument):
    """Document class representing a database object (schema, table, etc.)"""

    def __init__(self, site, dbobject):
        # Set dbobject before calling the inherited method to ensure that
        # site.add_document knows what object we represent
        self.dbobject = dbobject
        # Override the identifier for the top-level document
        if isinstance(dbobject, Database):
            ident = site.top or dbobject.identifier
        else:
            ident = dbobject.identifier
        super(HTMLObjectDocument, self).__init__(site, '%s.html' % ident)
        self.title = '%s %s' % (
            self.site.type_name(self.dbobject),
            self.dbobject.qualified_name
        )
        self.description = self.dbobject.description or self.title
        self.keywords = [
            self.site.database.name,
            self.site.type_name(self.dbobject),
            self.dbobject.name,
            self.dbobject.qualified_name
        ]

    def _get_first(self):
        result = super(HTMLObjectDocument, self)._get_first()
        if not result and self.dbobject.first:
            result = self.site.object_document(self.dbobject.first)
            self.first = result
        return result

    def _get_prior(self):
        result = super(HTMLObjectDocument, self)._get_prior()
        if not result and self.dbobject.prior:
            result = self.site.object_document(self.dbobject.prior)
            self.prior = result
        return result

    def _get_next(self):
        result = super(HTMLObjectDocument, self)._get_next()
        if not result and self.dbobject.next:
            result = self.site.object_document(self.dbobject.next)
            self.next = result
        return result

    def _get_last(self):
        result = super(HTMLObjectDocument, self)._get_last()
        if not result and self.dbobject.last:
            result = self.site.object_document(self.dbobject.last)
            self.last = result
        return result

    def _get_parent(self):
        result = super(HTMLObjectDocument, self)._get_parent()
        if not result and self.dbobject.parent:
            result = self.site.object_document(self.dbobject.parent)
            self.parent = result
        return result

    def generate_head(self):
        head = super(HTMLObjectDocument, self).generate_head()
        # Add the stylesheet to support the format_sql() method
        head.append(self.site.sql_style.link())
        return head

    def format_sql(self, sql, terminator=';', number_lines=False, id=None):
        # Overridden to add line number toggling capability (via jQuery)
        result = super(HTMLObjectDocument, self).format_sql(sql, terminator, number_lines, id)
        if number_lines and id:
            result = (result,
                self.tag.script("""
                    $(document).ready(function() {
                        $('#%(id)s').before(
                            $(document.createElement('p')).append(
                                $(document.createElement('a'))
                                    .append('Toggle line numbers')
                                    .attr('href', '#')
                                    .click(function() {
                                        $('#%(id)s').toggleClass('hide-num');
                                        return false;
                                    })
                            ).addClass('toggle')
                        );
                    });
                """ % {'id': id}))
        return result


class GraphDocument(WebSiteDocument):
    """Represents a document containing a GraphViz generated graph.

    This is the base class for image documents generated by GraphViz. It
    provides a doc attribute which is an ObjectGraph object from this module.
    This, along with pygraphviz provides rudimentary editing facilities for
    constructing dot graphs.
    """

    def __init__(self, site, url, alt=''):
        super(GraphDocument, self).__init__(site, url)
        self.mimetype = {
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.svg': 'image/svg+xml',
            '.ps':  'application/postscript',
            '.eps': 'application/postscript',
        }[os.path.splitext(self.filename)[1].lower()]
        self.alt = alt
        # PNGs and GIFs use a client-side image-map to define link locations
        # (SVGs just use embedded links)
        self.usemap = os.path.splitext(self.filename)[1].lower() in ('.png', '.gif')

    def generate(self):
        graph = self.site.graph_class(self.site, 'G')
        return graph

    def serialize(self, content):
        if isinstance(content, ObjectGraph):
            # The following lookup tables are used to decide on the method used
            # to write output based on the extension of the image filename
            ext = os.path.splitext(self.filename)[1].lower()
            try:
                method = {
                    '.png': content.to_png,
                    '.svg': content.to_svg,
                }[ext]
            except KeyError:
                raise Exception('Unknown image extension "%s"' % ext)
            result = StringIO()
            method(result)
            return result.getvalue()
        else:
            return super(GraphDocument, self).serialize(content)

    def write_broken(self, msg):
        # Called when something goes wrong in the write() method, which it
        # often does when dealing with truly massive graphs (GraphViz sometimes
        # crashes out or just writes garbage). This method simply logs some
        # warnings, and moves the resulting file (if any) out of the way to
        # prevent browsers potentially attempting to access corrupt files
        # (which in the case of buggy browsers could crash them), while
        # allowing investigation of the corrupt file.
        logging.warning(msg)
        if os.path.exists(self.filename):
            newname = '%s.broken' % self.filename
            logging.warning('Moving potentially corrupt image file "%s" to "%s"' % (self.filename, newname))
            if os.path.exists(newname):
                os.unlink(newname)
            os.rename(self.filename, newname)

    def write(self):
        try:
            super(GraphDocument, self).write()
        except Exception, e:
            self.write_broken('An error occurred while writing image "%s": %s' % (self.filename, e))

    def link(self, *args, **kwargs):
        if self.usemap:
            # If the graph uses a client side image map for links a bit
            # more work is required. We need to get the graph to generate
            # the <map> doc, then import all elements from that
            map = self.map()
            img = self.tag.img(src=self.url, usemap='#' + map.attrib['id'], alt=self.alt)
            return (img, map)
        else:
            return self.tag.img(src=self.url, alt=self.alt)

    def map(self):
        """Returns an Element containing the client-side image map."""
        assert self.usemap
        f = StringIO()
        try:
            self.generate().to_map(f)
            result = fromstring(f.getvalue())
            result.attrib['id'] = self.url.rsplit('.', 1)[0] + '.map'
            result.attrib['name'] = result.attrib['id']
            return result
        finally:
            f.close()


class GraphObjectDocument(GraphDocument):
    """Graph class representing a database object (schema, table, etc.)"""

    def __init__(self, site, dbobject):
        """Initializes an instance of the class."""
        self.dbobject = dbobject # must be set before calling the inherited method
        super(GraphObjectDocument, self).__init__(site,
            url='%s.png' % dbobject.identifier,
            alt='Diagram of %s' % dbobject.qualified_name)


# Declare classes for all the static documents in the default HTML plugin

class SQLStyle(StyleDocument):
    def __init__(self, site):
        super(SQLStyle, self).__init__(site, 'sql.css', resource_stream(__name__, 'sql.css'))

class ThickboxStyle(StyleDocument):
    def __init__(self, site):
        super(ThickboxStyle, self).__init__(site, 'thickbox.css', resource_stream(__name__, 'thickbox.css'))

class ThickboxScript(ScriptDocument):
    def __init__(self, site):
        super(ThickboxScript, self).__init__(site, 'thickbox.js', resource_stream(__name__, 'thickbox.js'))

class ThickboxImage(ImageDocument):
    def __init__(self, site):
        super(ThickboxImage, self).__init__(site, 'macFFBgHack.png', resource_stream(__name__, 'macFFBgHack.png'))

class JQueryScript(ScriptDocument):
    def __init__(self, site):
        super(JQueryScript, self).__init__(site, 'jquery.js', resource_stream(__name__, 'jquery.js'))

class JQueryUIScript(ScriptDocument):
    def __init__(self, site):
        super(JQueryScript, self).__init__(site, 'jquery.ui.all.js', resource_stream(__name__, 'jquery.ui.all.js'))

class TablesorterScript(ScriptDocument):
    def __init__(self, site):
        super(TablesorterScript, self).__init__(site, 'jquery.tablesorter.js', resource_stream(__name__, 'jquery.tablesorter.js'))
