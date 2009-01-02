# vim: set noet sw=4 ts=4:

"""Implements basic classes for generating graphs in the DOT language.

This unit implements a set of simple classes which provide facilities for
creating and performing basic manipulations of graphs in the GraphViz DOT
language. No facilities for parsing existing DOT language files are provided,
only for creating DOT files and image files by passing the DOT output through
GraphViz.

"""

import sys
mswindows = sys.platform.startswith('win')
import os
import re
from subprocess import Popen, PIPE, STDOUT
try:
	from cStringIO import StringIO
except ImportError:
	from StringIO import StringIO

DEFAULT_CONVERTER = 'dot'
SVG_FORMAT = 'svg'
GIF_FORMAT = 'gif'
PNG_FORMAT = 'png'
PS_FORMAT = 'ps2'
PDF_FORMAT = 'pdf'
MAP_FORMAT = 'cmapx'

# XXX Add some code to check for duplicate graph/node/edge IDs

class GraphError(Exception): pass

class GraphConvertError(GraphError): pass

class GraphObject(object):
	"""Base class for all objects in the module.

	The GraphObject class separates all graphing attributes (shape, style,
	label, etc.) into a separate dictionary of values, which only contains
	entries for those attributes which have been explicitly assigned a new
	value. This helps makes the in memory representation of a graph a bit more
	minimal, and makes extracting the attributes for writing much easier &
	quicker.

	It also provides utility methods for determining when and how to quote
	identifiers in the dot language, for obtaining a formatted list of
	attributes and their values, and for some basic methods for navigating the
	hierarchy of objects.
	"""
	_attributes = frozenset()

	def __init__(self):
		super(GraphObject, self).__setattr__('_attr_values', {})
		super(GraphObject, self).__init__()

	def __getattribute__(self, name):
		try:
			return super(GraphObject, self).__getattribute__('_attr_values')[name]
		except KeyError:
			if name in super(GraphObject, self).__getattribute__('_attributes'):
				return None
			else:
				return super(GraphObject, self).__getattribute__(name)

	def __setattr__(self, name, value):
		if name in self._attributes:
			self.__dict__['_attr_values'][name] = value
		else:
			object.__setattr__(self, name, value)

	dot_alpha_ident = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
	dot_num_ident = re.compile(r'^-?(\.[0-9]+|[0-9]+(\.[0-9]*)?)$')

	def _quote(self, s):
		"""Internal utility method for quoting identifiers if they need to be"""
		if s == '' or self.dot_alpha_ident.match(s) or self.dot_num_ident.match(s):
			return s
		else:
			s = s.replace('"', '\\"')
			s = s.replace('\n', '\\n')
			s = s.replace('\r', '\\r')
			s = s.replace('\t', '\\t')
			return '"%s"' % s
	
	def _attr_values_str(self):
		"""Internal utility method that returns _attr_values as a formatted string"""
		return ', '.join(
			'%s=%s' % (self._quote(n), self._quote(str(v)))
			for (n, v) in self._attr_values.iteritems()
		)
	
	def _get_graph(self):
		"""Returns the top-level graph that owns the object"""
		o = self
		while o is not None and not isinstance(o, Graph):
			o = o.parent
		if o:
			return o
		else:
			raise Exception('Unable to find top-level Graph object')

	def _get_dot(self):
		"""Returns a string containing the dot-language representation of the object"""
		# Stub to be overridden by child classes
		pass

	graph = property(_get_graph)
	dot = property(lambda self: self._get_dot())


class GraphBase(GraphObject):
	"""Base class for all graph objects"""

	def __init__(self, id):
		"""Initializes an instance of the class.
		
		The id parameter specifies the id of the graph. Each object in a
		graphviz graph must have a unique identifier.
		"""
		super(GraphBase, self).__init__()
		self.children = []
		self.parent = None
		self.id = id


class Graph(GraphBase):
	"""Class representing a top level graph"""

	_attributes = frozenset(('Damping', 'K', 'URL', 'bb', 'bgcolor', 'center',
		'charset', 'clusterrank', 'colorscheme', 'comment', 'compound',
		'concentrate', 'defaultdist', 'dim', 'diredgeconstraints', 'dpi',
		'epsilon', 'esep', 'fontcolor', 'fontname', 'fontpath', 'fontsize',
		'label', 'labeljust', 'labelloc', 'landscape', 'layers', 'layersep',
		'levelsgap', 'lp', 'margin', 'maxiter', 'mclimit', 'mindist', 'mode',
		'model', 'mosek', 'nodesep', 'normalize', 'nslimit1', 'ordering',
		'orientation', 'outputorder', 'overlap', 'pack', 'packmode', 'page',
		'pagedir', 'quantum', 'rankdir', 'ranksep', 'ratio', 'remincross',
		'resolution', 'root', 'rotate', 'searchsize', 'sep', 'showboxes',
		'size', 'splines', 'start', 'stylesheet', 'target', 'truecolor',
		'viewport', 'voro_margin'))

	def __init__(self, id, directed=True, strict=False):
		"""Initializes an instance of the class.

		The id parameter specifies the id of the graph. The optional directed
		parameter specifies whether the graph is directed (each edge is one
		way) or undirected (each edge is bidirectional). If the strict
		parameter is True, then cycles and multi-edges in a directed graph will
		be ignored.
		"""
		super(Graph, self).__init__(id)
		self.directed = directed
		self.strict = strict

	def _get_dot(self):
		keys = {
			'strict':     ['', 'strict '][self.strict and self.directed],
			'type':       ['graph', 'digraph'][self.directed],
			'id':         self._quote(str(self.id)),
			'attributes': self._attr_values_str(),
			'children':   '\n\t'.join(c.dot + ';' for c in self.children),
		}
		return """\
%(strict)s%(type)s %(id)s {
	graph [%(attributes)s];
	%(children)s
}""" % keys

	def _call_graphviz(self, output, converter, format, graph_attr, node_attr, edge_attr):
		"""Internal utility method use by the various to_X conversion methods."""
		cmd_line = [converter, '-T%s' % format]
		if graph_attr:
			cmd_line.extend(['-G%s=%s' % (n, v) for (n, v) in graph_attr.iteritems()])
		if node_attr:
			cmd_line.extend(['-N%s=%s' % (n, v) for (n, v) in node_attr.iteritems()])
		if edge_attr:
			cmd_line.extend(['-E%s=%s' % (n, v) for (n, v) in edge_attr.iteritems()])
		p = Popen(cmd_line, stdin=PIPE, stdout=PIPE, close_fds=not mswindows)
		try:
			stdout, stderr = p.communicate(self.dot)
			output.write(stdout)
		finally:
			if p.wait() != 0:
				raise GraphConvertError('graphviz converter %s exited with code %d\n%s' % (converter, p.returncode, stderr))

	svg_fix = re.compile(r'(style=".*font-size:\s*[0-9]*(\.[0-9]+)?)(\s*;.*")')
	def to_svg(self, output, converter=DEFAULT_CONVERTER, graph_attr=None, node_attr=None, edge_attr=None):
		"""Converts the Graph into an SVG image.

		Parameters:
		output -- A file-like object to write the SVG to
		converter -- The path and name of the GraphViz application to use
		graph_attr -- An optional dictionary of graph attributes to pass on the command line
		node_attr -- An optional dictionary of node attributes to pass on the command line
		edge_attr -- An optional dictionary of edge attributes to pass on the command line
		"""
		s = StringIO()
		self._call_graphviz(s, converter, SVG_FORMAT, graph_attr, node_attr, edge_attr)
		# XXX Workaround: Fix a bug in GraphViz's SVG output; the font-size
		# style element needs a unit, usually px, to work correctly in Firefox,
		# Opera, etc.
		output.write(self.svg_fix.sub(r'\1px\3', s.getvalue()))

	def to_ps(self, output, converter=DEFAULT_CONVERTER, graph_attr=None, node_attr=None, edge_attr=None):
		"""Converts the Graph into a PostScript document.

		Parameters are identical to the to_svg() method.
		"""
		self._call_graphviz(output, converter, PS_FORMAT, graph_attr, node_attr, edge_attr)

	def to_pdf(self, output, converter=DEFAULT_CONVERTER, graph_attr=None, node_attr=None, edge_attr=None):
		"""Converts the Graph into a PDF document.

		Parameters are identical to the to_svg() method.
		"""
		self._call_graphviz(output, converter, PDF_FORMAT, graph_attr, node_attr, edge_attr)

	def to_png(self, output, converter=DEFAULT_CONVERTER, graph_attr=None, node_attr=None, edge_attr=None):
		"""Converts the Graph into a PNG image (and optionally a client-side image-map).

		Parameters are identical to the to_svg() method.
		"""
		self._call_graphviz(output, converter, PNG_FORMAT, graph_attr, node_attr, edge_attr)
	
	def to_gif(self, output, converter=DEFAULT_CONVERTER, graph_attr=None, node_attr=None, edge_attr=None):
		"""Converts the Graph into a GIF image (and optionally a client-side image-map).

		Parameters are identical to the to_svg() method.
		"""
		self._call_graphviz(output, converter, GIF_FORMAT, graph_attr, node_attr, edge_attr)
	
	def to_map(self, output, converter=DEFAULT_CONVERTER, graph_attr=None, node_attr=None, edge_attr=None):
		"""Converts the Graph into a client-side image map.

		Parameters are identical to the to_svg() method.
		"""
		self._call_graphviz(output, converter, MAP_FORMAT, graph_attr, node_attr, edge_attr)

	def __iter__(self):
		"""Generator method which yields every object within the graph."""
		def iter_sub(subgraph):
			assert isinstance(subgraph, GraphBase)
			yield subgraph
			for item in subgraph.children:
				if isinstance(item, GraphBase):
					for subitem in iter_sub(item):
						yield subitem
				else:
					yield item
		return iter_sub(self)
	
	def touch(self, method, *args, **kwargs):
		"""Calls the specified method for each object within the graph.

		The touch() method can be used to perform an operation on all objects
		or a sub-set of all objects in the graph. It iterates over all children
		of the graph, recursing into Subgraphs and Clusters. The specified
		method is called for each object with a single parameter (namely, the
		object).

		Additional parameters can be passed which will be captured by args and
		kwargs and passed verbatim to method on each invocation.

		The return value of the method can control when the recursion
		terminates.  If the method returns a value which evaluates to True, the
		loop immediately terminates.  If the method returns a value which
		evaluates to False (e.g. if it returns None which all functions do by
		default if no return is specified), the loop continues.
		"""
		for item in self:
			if method(item, *args, **kwargs):
				return True


class Subgraph(GraphBase):
	"""Class representing a subgraph within a graph (or subgraph)"""

	_attributes = frozenset(('rank'))

	def __init__(self, graph, id):
		"""Initializes an instance of the class.
		
		The id parameter specifies the id of the graph. Each object in a
		graphviz graph must have a unique identifier.
		"""
		assert isinstance(graph, GraphBase)
		super(Subgraph, self).__init__(id)
		self.parent = graph
		graph.children.append(self)

	def _get_dot(self):
		keys = {
			'id':         self._quote(str(self.id)),
			'attributes': self._attr_values_str(),
			'children':   '\n\t'.join(c.dot + ';' for c in self.children),
		}
		return """\
subgraph %(id)s {
	graph [%(attributes)s];
	%(children)s
}""" % keys


class Cluster(Subgraph):
	"""Class representing a cluster-style subgraph within a top-level graph"""

	_attributes = frozenset(('K', 'URL', 'bgcolor', 'color', 'colorscheme',
		'fillcolor', 'fontcolor', 'fontname', 'fontsize', 'label', 'labeljust',
		'labelloc', 'lp', 'nojustify', 'pencolor', 'penwidth', 'peripheries',
		'style', 'target', 'tooltip'))

	def __init__(self, graph, id):
		"""Initializes an instance of the class.
		
		The id parameter specifies the id of the graph. Each object in a
		graphviz graph must have a unique identifier.
		"""
		assert isinstance(graph, Graph)
		super(Cluster, self).__init__(graph, id)
		# XXX Hmm ... need to ensure id is provided and is unique with cluster_ prefix
	
	def _get_dot(self):
		# A cluster is just a specially named subgraph, so we just rewrite the
		# id temporarily and call the inherited method
		save_id = self.id
		self.id = 'cluster_%s' % self.id
		result = super(Cluster, self)._get_dot()
		self.id = save_id
		return result


class Node(GraphObject):
	"""Class representing a node or vertex in a graph"""

	_attributes = frozenset(('URL', 'color', 'comment', 'distortion',
		'fillcolor', 'fixedsize', 'fontcolor', 'fontname', 'fontsize', 'group',
		'height', 'label', 'layer', 'margin', 'nojustify', 'orientation',
		'penwidth', 'peripheries', 'pin', 'pos', 'rects', 'regular', 'root',
		'samplepoints', 'shape', 'shapefile', 'showboxes', 'sides', 'skew',
		'style', 'target', 'tooltip', 'vertices', 'width', 'z'))

	def __init__(self, graph, id):
		"""Initializes an instance of the class.
		
		The id parameter specifies the id of the node. Each object in a
		graphviz graph must have a unique identifier.
		"""
		assert isinstance(graph, GraphBase)
		super(Node, self).__init__()
		self.parent = graph
		self.id = id
		graph.children.append(self)
	
	def _get_dot(self):
		return '%s [%s]' % (
			self._quote(str(self.id)),
			self._attr_values_str()
		)

	def connect_to(self, node):
		"""Connects this node to the specified node.

		The connect_to() method creates an Edge object (which it returns) which
		connects the object the method is called on to the node specified in
		the single parameter. If this node is already connected to the
		specified node, the existing connection will be returned instead of
		creating a new one.
		"""
		assert isinstance(node, Node)
		assert self.graph == node.graph
		return self.is_connected_to(node) or Edge(self.graph, self, node)

	def disconnect_from(self, node):
		"""Removes all connections between this node and the specified node.

		The disconnect_from() method searches for all Edge objects connecting
		from the node on which the method is called to the node specified in
		the parameter, and destroys them.  Note that if the graph is directed,
		this will NOT remove connections from the node specified in the
		parameter to the node on which the method is called.
		"""
		assert isinstance(node, Node)
		assert self.graph == node.graph

		def disconnect_directed(i, node, edges):
			if isinstance(i, Edge) and i.from_node == self and i.to_node == node:
				edges.append(i)

		def disconnect_undirected(i, node, edges):
			if isinstance(i, Edge) and ((i.from_node == self and i.to_node == node) or
					(i.from_node == node and i.to_node == self)):
				edges.append(i)

		edges = []
		if self.graph.directed:
			self.graph.touch(disconnect_directed, node=node, edges=edges)
		else:
			self.graph.touch(disconnect_undirected, node=node, edges=edges)
		for edge in edges:
			edge.parent.children.remove(edge)

	def is_connected_to(self, node):
		"""Determines if this node is connected to the specified node.

		The is_connected_to() method recursively searches the graph for Edge
		objects connecting the from the node on which the method is called to
		the node specified in the parameter. If such an Edge is found it is
		returned. If no such Edge is found, None is returned.
		
		If the graph is undirected, the method also searches for reverse
		connections (from the specified node to this node).
		"""
		assert isinstance(node, Node)
		assert self.graph == node.graph
		edge = [None]

		def find_directed(i, node, edge):
			if isinstance(i, Edge) and i.from_node == self and i.to_node == node:
				edge[0] = i
				return True

		def find_undirected(i, node, edge):
			if isinstance(i, Edge) and ((i.from_node == self and i.to_node == node) or
					(i.from_node == node and i.to_node == self)):
				edge[0] = i
				return True

		if self.graph.directed:
			self.graph.touch(find_directed, node=node, edge=edge)
		else:
			self.graph.touch(find_undirected, node=node, edge=edge)
		return edge[0]


class Edge(GraphObject):
	"""Class representing an edge between two nodes in a graph"""

	_attributes = frozenset(('URL', 'arrowhead', 'arrowsize', 'arrowtail',
		'color', 'comment', 'constraint', 'decorate', 'dir', 'fontcolor',
		'fontname', 'fontsize', 'headURL', 'headclip', 'headhref', 'headlabel',
		'headport', 'headtarget', 'headtooltip', 'href', 'label', 'labelangle',
		'labeldistance', 'labelfloat', 'labelfontcolor', 'labelfontname',
		'labelfontsize', 'layer', 'len', 'lhead', 'lp', 'ltail', 'minlen',
		'nojustify', 'penwidth', 'pos', 'samehead', 'sametail', 'showboxes',
		'style', 'tailURL', 'tailclip', 'tailhref', 'taillabel', 'tailport',
		'tailtarget', 'tailtooltip', 'target', 'tooltip', 'weight'))

	def __init__(self, graph, from_node, to_node):
		"""Initializes an instance of the class.

		The graph parameter specifies the graph (or subgraph) that the edge
		belongs to. The from_node and to_node parameter provide the nodes that
		the edge connects. If the graph is undirected, the edge effectively
		joins to_node to from_node as well.
		"""
		super(Edge, self).__init__()
		assert isinstance(graph, GraphBase)
		assert isinstance(from_node, Node)
		assert isinstance(to_node, Node)
		self.parent = graph
		self.from_node = from_node
		self.to_node = to_node
		graph.children.append(self)

	def _get_dot(self):
		return '%s %s %s [%s]' % (
			self._quote(str(self.from_node.id)),
			['--', '->'][self.graph.directed],
			self._quote(str(self.to_node.id)),
			self._attr_values_str(),
		)
