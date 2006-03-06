#!/usr/bin/env python
# $Header$
# vim: set noet sw=4 ts=4:

import logging
import doccache
import docdatabase
import docoutput_w3

def main():
	# Configure the output
	#logging.basicConfig(level = logging.INFO)
	# Find a suitable connection library and create a database connection
	try:
		import DB2
		connection = DB2.Connection("DQSMS")
	except ImportError:
		import dbi
		import odbc
		connection = odbc.odbc("DQSMS/dave/St4rGate")
	try:
		print "Building metadata cache"
		cache = doccache.DocCache(connection)
		print "Building database object hierarchy"
		database = docdatabase.DocDatabase(cache, "DQSMS")
		print "Writing output with w3 handler"
		docoutput_w3.DocOutput(database, "../public_html/dqsms")
	finally:
		connection.close()
		connection = None

if __name__ == '__main__':
	main()
