# vim: set noet sw=4 ts=4:

import sys
import logging
import dbsuite.script
import dbsuite.tokenizer
import dbsuite.plugins
import dbsuite.main
import ConfigParser
import optparse
try:
	import cPickle as pickle
except ImportError:
	import pickle
from dbsuite.compat import *

class MyConfigParser(ConfigParser.SafeConfigParser):
	"""Tweaked version of SaveConfigParser that uses uppercase for keys"""
	def optionxform(self, optionstr):
		return optionstr.upper()

class ListHandler(logging.Handler):
	"""An extremely basic logging handler which simply remembers all LogRecords"""
	def __init__(self):
		logging.Handler.__init__(self)
		self.records = []
	def emit(self, record):
		self.records.append(record)

class ExecSqlUtility(dbsuite.main.Utility):
	"""%prog [options] files...

	This utility executes multiple SQL scripts. If possible (based on a files
	produced/consumed analysis) it will run scripts in parallel, reducing
	execution time. Either specify the names of files containing the SQL to
	execute, or specify - to indicate that stdin should be read. List-files
	(prefixed with @) are also accepted as a method of specifying input files.
	"""

	def __init__(self):
		super(ExecSqlUtility, self).__init__()
		self.parser.set_defaults(
			autocommit=False,
			config='',
			deletefiles=False,
			test=0,
			retry=1,
			stoponerror=False,
			terminator=';',
			execinternal=False
		)
		self.parser.add_option('-t', '--terminator', dest='terminator',
			help="""specify the statement terminator (default=';')""")
		self.parser.add_option("-a", "--auto-commit", dest="autocommit", action="store_true",
			help="""automatically COMMIT after each SQL statement in a script""")
		self.parser.add_option("-c", "--config", dest="config",
			help="""specify the configuration file""")
		self.parser.add_option("-d", "--delete-files", dest="deletefiles", action="store_true",
			help="""delete files produced by the scripts after execution""")
		self.parser.add_option("-n", "--dry-run", dest="test", action="count",
			help="""test but don't run the scripts, can be specified multiple times: 1x=parse, 2x=test file perms, 3x=test db logins""")
		self.parser.add_option("-r", "--retry", dest="retry", type="int",
			help="""specify the maximum number of retries after script failure (default: %default)""")
		self.parser.add_option("-s", "--stop-on-error", dest="stoponerror", action="store_true",
			help="""if a script encounters an error stop it immediately""")
		self.parser.add_option("--exec-internal", dest="execinternal", action="store_true",
			help=optparse.SUPPRESS_HELP)

	def main(self, options, args):
		super(ExecSqlUtility, self).main(options, args)
		if options.execinternal:
			# We've been called by a parent dbexec instance to execute an SQL
			# script. Firstly, set up logging to just capture LogRecord objects
			log = logging.getLogger()
			while log.handlers:
				log.removeHandler(log.handlers[-1])
			log.addHandler(ListHandler())
			if options.debug:
				console = logging.StreamHandler(sys.stderr)
				console.setFormatter(logging.Formatter('%(message)s'))
				console.setLevel(logging.DEBUG)
				log.addHandler(console)
			try:
				# Then reconstruct the pickled SQLScript that's been passed on stdin
				# and run its exec_internal method
				script = pickle.load(sys.stdin)
				returncode = script._exec_internal()
			finally:
				# Finally, pickle the LogRecord objects and dump them to stdout
				# before exiting with the appropriate returncode
				pickle.dump(log.handlers[0].records, sys.stdout)
				return returncode
		else:
			# This is a normal dbexec run
			config = {}
			if options.config:
				config = self.process_config(options.config)
			done_stdin = False
			sql_files = []
			for sql_file in args:
				if sql_file == '-':
					if not done_stdin:
						done_stdin = True
						sql_file = sys.stdin
					else:
						raise IOError('Cannot read input from stdin multiple times')
				else:
					sql_file = open(sql_file, 'rU')
				sql_files.append(sql_file)
			plugin = dbsuite.plugins.load_plugin('db2.luw')()
			job = dbsuite.script.SQLJob(plugin, sql_files, vars=config,
				terminator=options.terminator, retrylimit=options.retry,
				autocommit=options.autocommit, stoponerror=options.stoponerror,
				deletefiles=options.deletefiles)
			if options.test == 0:
				job.test_connections()
				job.test_permissions()
				job.execute(debug=options.debug)
			else:
				if options.test > 2:
					job.test_connections()
				if options.test > 1:
					job.test_permissions()
				logging.info('')
				logging.info('Dependency tree:')
				job.print_dependencies()
				logging.info('Data transfers:')
				job.print_transfers()
				for script in job.depth_traversal():
					logging.info('')
					logging.info(script.filename)
					# Write SQL to stdout so it can be redirected if necessary
					sys.stdout.write(script.sql)
					sys.stdout.write('\n')
					sys.stdout.flush()
			return 0

	def handle(self, type, value, tb):
		"""Exception hook for non-debug mode."""
		if issubclass(type, (dbsuite.script.Error, dbsuite.tokenizer.Error)):
			# For script errors, just output the message which should be
			# sufficient for the end user (no need to confuse them with a full
			# stack trace)
			logging.critical(str(value))
			return 3
		else:
			super(ExecSqlUtility, self).handle(type, value, tb)

	def process_config(self, config_file):
		"""Reads and parses an Ini-style configuration file.

		The config_file parameter specifies a configuration filename to
		process. The routine parses the file looking for a section named
		[Substitute]. The contents of this section will be returned as a
		dictionary to the caller.
		"""
		config = MyConfigParser()
		logging.info('Reading configuration file %s' % config_file)
		if not config.read(config_file):
			raise IOError('Unable to read configuration file %s' % config_file)
		if not 'Substitute' in config.sections():
			logging.warning('The configuration file %s has no [Substitute] section' % config_file)
		return dict(config.items('Substitute'))

main = ExecSqlUtility()
