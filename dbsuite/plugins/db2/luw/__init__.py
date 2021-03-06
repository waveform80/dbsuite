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

"""Input plugin for IBM DB2 for Linux/UNIX/Windows."""

from __future__ import (
    unicode_literals,
    print_function,
    absolute_import,
    division,
    )

import logging
import re

import dbsuite.plugins
from dbsuite.plugins.db2 import (
    connect, make_datetime, make_bool, make_int, make_str
)
from dbsuite.plugins.db2.luw.tokenizer import DB2LUWTokenizer
from dbsuite.plugins.db2.luw.parser import DB2LUWParser, DB2LUWScriptParser
from dbsuite.tuples import (
    Schema, Datatype, Table, View, Alias, RelationDep, Index, IndexCol,
    RelationCol, UniqueKey, UniqueKeyCol, ForeignKey, ForeignKeyCol, Check,
    CheckCol, Function, Procedure, RoutineParam, Trigger, TriggerDep,
    Tablespace
)


class InputPlugin(dbsuite.plugins.InputPlugin):
    """Input plugin for IBM DB2 for Linux/UNIX/Windows.

    This input plugin supports extracting documentation information from IBM
    DB2 for Linux/UNIX/Windows version 8.2 or above. If the DOCCAT schema (see
    the doccat_create.sql script in the contrib/db2/luw directory) is present,
    it will be used to source documentation data instead of SYSCAT.
    """

    def __init__(self):
        super(InputPlugin, self).__init__()
        self.add_option(
            'database', default='', doc='The locally cataloged name of the '
            'database to connect to')
        self.add_option(
            'username', default=None, doc='The username to connect with (if '
            'omitted, an implicit connection will be made as the current user)')
        self.add_option(
            'password', default=None, doc='The password associated with the '
            'user given by the username option (mandatory if username is '
            'supplied)')

    def tokenizer(self):
        return DB2LUWTokenizer()

    def parser(self, for_scripts=False):
        if for_scripts:
            return DB2LUWScriptParser()
        else:
            return DB2LUWParser()

    def configure(self, config):
        """Loads the plugin configuration."""
        super(InputPlugin, self).configure(config)
        # Check for missing stuff
        if not self.options['database']:
            raise dbsuite.plugins.PluginConfigurationError(
                'The database option must be specified')
        if self.options['username'] is not None and self.options['password'] is None:
            raise dbsuite.plugins.PluginConfigurationError(
                'If the username option is specified, the password option must also be specified')

    def get_version(self):
        # Test which version of the system catalog is installed. The following
        # progression is used to determine version:
        #
        # Unknown level (0)
        # SYSCAT.ROUTINES introduced in v8.2 (82)
        # SYSCAT.TABLES.OWNER introduced in v9.1 (91)
        # SYSCAT.VARIABLES introduced in v9.5 (95)
        # SYSCAT.MODULES introduced in v9.7 (97)
        # SYSCAT.PERIODS introduced in v10.1 (101)
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT COUNT(*)
            FROM SYSCAT.TABLES
            WHERE TABSCHEMA = 'SYSCAT'
            AND TABNAME = 'PERIODS'
            WITH UR""")
        if bool(cursor.fetchall()[0][0]):
            return 101
        cursor.execute("""
            SELECT COUNT(*)
            FROM SYSCAT.TABLES
            WHERE TABSCHEMA = 'SYSCAT'
            AND TABNAME = 'MODULES'
            WITH UR""")
        if bool(cursor.fetchall()[0][0]):
            return 97
        cursor.execute("""
            SELECT COUNT(*)
            FROM SYSCAT.TABLES
            WHERE TABSCHEMA = 'SYSCAT'
            AND TABNAME = 'VARIABLES'
            WITH UR""")
        if bool(cursor.fetchall()[0][0]):
            return 95
        cursor.execute("""
            SELECT COUNT(*)
            FROM SYSCAT.COLUMNS
            WHERE TABSCHEMA = 'SYSCAT'
            AND TABNAME = 'TABLES'
            AND COLNAME = 'OWNER'
            WITH UR""")
        if bool(cursor.fetchall()[0][0]):
            return 91
        cursor.execute("""
            SELECT COUNT(*)
            FROM SYSCAT.TABLES
            WHERE TABSCHEMA = 'SYSCAT'
            AND TABNAME = 'ROUTINES'
            WITH UR""")
        if bool(cursor.fetchall()[0][0]):
            return 82
        return 0

    def open(self):
        """Opens the database connection for data retrieval."""
        super(InputPlugin, self).open()
        self.connection = connect(
            self.options['database'],
            self.options['username'],
            self.options['password']
        )
        self.name = self.options['database']
        # Test whether the DOCCAT extension is installed
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT COUNT(*)
            FROM SYSCAT.SCHEMATA
            WHERE SCHEMANAME = 'DOCCAT'
            WITH UR""")
        doccat = bool(cursor.fetchall()[0][0])
        logging.info([
            'DOCCAT extension schema not found, using SYSCAT',
            'DOCCAT extension schema found, using DOCCAT instead of SYSCAT'
        ][doccat])
        version = self.get_version()
        logging.info({
            82:  'Detected v8.2 catalog layout',
            91:  'Detected v9.1 catalog layout',
            95:  'Detected v9.5 catalog layout',
            97:  'Detected v9.7 catalog layout',
            101: 'Detected v10.1 (or later) catalog layout',
        }.get(version, 'Unknown or ancient catalog layout'))
        if not version:
            raise dbsuite.plugins.PluginError('DB2 server must be v8.2 or above')
        # Set up a generic query substitution dictionary
        self.query_subst = {
            'schema': ['SYSCAT', 'DOCCAT'][doccat],
            'owner': ['DEFINER', 'OWNER'][version >= 91],
        }

    def close(self):
        """Closes the database connection and cleans up any resources."""
        super(InputPlugin, self).close()
        self.connection.close()
        del self.connection

    def get_schemas(self):
        """Retrieves the details of schemas stored in the database.

        Override this function to return a list of Schema tuples containing
        details of the schemas defined in the database. Schema tuples have the
        following named fields:

        name         -- The name of the schema
        owner*       -- The name of the user who owns the schema
        system       -- True if the schema is system maintained (bool)
        created*     -- When the schema was created (datetime)
        description* -- Descriptive text

        * Optional (can be None)
        """
        for row in super(InputPlugin, self).get_schemas():
            yield row
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT
                RTRIM(SCHEMANAME) AS NAME,
                RTRIM(OWNER)      AS OWNER,
                CASE
                    WHEN SCHEMANAME LIKE 'SYS%%' THEN 'Y'
                    WHEN SCHEMANAME = 'SQLJ' THEN 'Y'
                    WHEN SCHEMANAME = 'NULLID' THEN 'Y'
                    ELSE 'N'
                END               AS SYSTEM,
                CHAR(CREATE_TIME) AS CREATED,
                REMARKS           AS DESCRIPTION
            FROM
                %(schema)s.SCHEMATA
            WITH UR""" % self.query_subst)
        for (
                name,
                owner,
                system,
                created,
                desc,
            ) in self.fetch_some(cursor):
            yield Schema(
                make_str(name),
                make_str(owner),
                make_bool(system),
                make_datetime(created),
                make_str(desc),
            )

    def get_datatypes(self):
        """Retrieves the details of datatypes stored in the database.

        Override this function to return a list of Datatype tuples containing
        details of the datatypes defined in the database (including system
        types). Datatype tuples have the following named fields:

        schema         -- The schema of the datatype
        name           -- The name of the datatype
        owner*         -- The name of the user who owns the datatype
        system         -- True if the type is system maintained (bool)
        created*       -- When the type was created (datetime)
        description*   -- Descriptive text
        variable_size  -- True if the type has a variable length (e.g. VARCHAR)
        variable_scale -- True if the type has a variable scale (e.g. DECIMAL)
        source_schema* -- The schema of the base system type of the datatype
        source_name*   -- The name of the base system type of the datatype
        size*          -- The length of the type for character based types or
                          the maximum precision for decimal types
        scale*         -- The maximum scale for decimal types

        * Optional (can be None)
        """
        for row in super(InputPlugin, self).get_datatypes():
            yield row
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT
                RTRIM(TYPESCHEMA)   AS TYPESCHEMA,
                RTRIM(TYPENAME)     AS TYPENAME,
                RTRIM(%(owner)s)    AS OWNER,
                CASE METATYPE
                    WHEN 'S' THEN 'Y'
                    ELSE 'N'
                END                 AS SYSTEM,
                CHAR(CREATE_TIME)   AS CREATED,
                REMARKS             AS DESCRIPTION,
                RTRIM(SOURCESCHEMA) AS SOURCESCHEMA,
                RTRIM(SOURCENAME)   AS SOURCENAME,
                NULLIF(LENGTH, 0)   AS SIZE,
                SCALE               AS SCALE
            FROM
                %(schema)s.DATATYPES
            WHERE INSTANTIABLE = 'Y'
            WITH UR""" % self.query_subst)
        for (
                schema,
                name,
                owner,
                system,
                created,
                desc,
                source_schema,
                source_name,
                size,
                scale,
            ) in self.fetch_some(cursor):
            system = make_bool(system)
            yield Datatype(
                make_str(schema),
                make_str(name),
                make_str(owner),
                system,
                make_datetime(created),
                make_str(desc),
                system and not size and (name not in ('XML', 'REFERENCE')),
                system and (name == 'DECIMAL'),
                make_str(source_schema),
                make_str(source_name),
                make_int(size),
                make_int(scale),
            )

    def get_tables(self):
        """Retrieves the details of tables stored in the database.

        Override this function to return a list of Table tuples containing
        details of the tables (NOT views) defined in the database (including
        system tables). Table tuples contain the following named fields:

        schema        -- The schema of the table
        name          -- The name of the table
        owner*        -- The name of the user who owns the table
        system        -- True if the table is system maintained (bool)
        created*      -- When the table was created (datetime)
        description*  -- Descriptive text
        tbspace       -- The name of the primary tablespace containing the table
        last_stats*   -- When the table's statistics were last calculated (datetime)
        cardinality*  -- The approximate number of rows in the table
        size*         -- The approximate size in bytes of the table

        * Optional (can be None)
        """
        for row in super(InputPlugin, self).get_tables():
            yield row
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT
                RTRIM(T.TABSCHEMA)                          AS TABSCHEMA,
                RTRIM(T.TABNAME)                            AS TABNAME,
                RTRIM(T.%(owner)s)                          AS OWNER,
                CHAR('N')                                   AS SYSTEM,
                CHAR(T.CREATE_TIME)                         AS CREATED,
                T.REMARKS                                   AS DESCRIPTION,
                COALESCE(RTRIM(T.TBSPACE), 'NICKNAMESPACE') AS TBSPACE,
                CHAR(T.STATS_TIME)                          AS LASTSTATS,
                NULLIF(T.CARD, -1)                          AS CARDINALITY,
                BIGINT(NULLIF(T.FPAGES, -1)) * TS.PAGESIZE  AS SIZE
            FROM
                %(schema)s.TABLES T
                LEFT OUTER JOIN %(schema)s.TABLESPACES TS
                    ON T.TBSPACEID = TS.TBSPACEID
            WHERE
                T.TYPE IN ('T', 'N')
                AND T.STATUS = 'N'
            WITH UR""" % self.query_subst)
        for (
                schema,
                name,
                owner,
                system,
                created,
                desc,
                tbspace,
                laststats,
                cardinality,
                size,
            ) in self.fetch_some(cursor):
            yield Table(
                make_str(schema),
                make_str(name),
                make_str(owner),
                make_bool(system),
                make_datetime(created),
                make_str(desc),
                make_str(tbspace),
                make_datetime(laststats),
                make_int(cardinality),
                make_int(size),
            )

    def get_views(self):
        """Retrieves the details of views stored in the database.

        Override this function to return a list of View tuples containing
        details of the views defined in the database (including system views).
        View tuples contain the following named fields:

        schema        -- The schema of the view
        name          -- The name of the view
        owner*        -- The name of the user who owns the view
        system        -- True if the view is system maintained (bool)
        created*      -- When the view was created (datetime)
        description*  -- Descriptive text
        read_only*    -- True if the view is not updateable (bool)
        sql*          -- The SQL statement that defined the view

        * Optional (can be None)
        """
        for row in super(InputPlugin, self).get_views():
            yield row
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT
                RTRIM(V.VIEWSCHEMA)   AS VIEWSCHEMA,
                RTRIM(V.VIEWNAME)     AS VIEWNAME,
                RTRIM(V.%(owner)s)    AS OWNER,
                CHAR('N')             AS SYSTEM,
                CHAR(T.CREATE_TIME)   AS CREATED,
                T.REMARKS             AS DESCRIPTION,
                V.READONLY            AS READONLY,
                V.TEXT                AS SQL
            FROM
                %(schema)s.TABLES T
                INNER JOIN %(schema)s.VIEWS V
                    ON T.TABSCHEMA = V.VIEWSCHEMA
                    AND T.TABNAME = V.VIEWNAME
                    AND T.TYPE = 'V'
            WHERE
                V.VALID = 'Y'
            WITH UR""" % self.query_subst)
        for (
                schema,
                name,
                owner,
                system,
                created,
                desc,
                readonly,
                sql,
            ) in self.fetch_some(cursor):
            yield View(
                make_str(schema),
                make_str(name),
                make_str(owner),
                make_bool(system),
                make_datetime(created),
                make_str(desc),
                make_bool(readonly),
                make_str(sql),
            )

    def get_aliases(self):
        """Retrieves the details of aliases stored in the database.

        Override this function to return a list of Alias tuples containing
        details of the aliases (also known as synonyms in some systems) defined
        in the database (including system aliases). Alias tuples contain the
        following named fields:

        schema        -- The schema of the alias
        name          -- The name of the alias
        owner*        -- The name of the user who owns the alias
        system        -- True if the alias is system maintained (bool)
        created*      -- When the alias was created (datetime)
        description*  -- Descriptive text
        base_schema   -- The schema of the target relation
        base_table    -- The name of the target relation

        * Optional (can be None)
        """
        for row in  super(InputPlugin, self).get_aliases():
            yield row
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT
                RTRIM(A.TABSCHEMA)      AS ALIASSCHEMA,
                RTRIM(A.TABNAME)        AS ALIASNAME,
                RTRIM(A.%(owner)s)      AS OWNER,
                CHAR('N')               AS SYSTEM,
                CHAR(A.CREATE_TIME)     AS CREATED,
                A.REMARKS               AS DESCRIPTION,
                RTRIM(A.BASE_TABSCHEMA) AS BASESCHEMA,
                RTRIM(A.BASE_TABNAME)   AS BASETABLE
            FROM
                %(schema)s.TABLES A
                INNER JOIN %(schema)s.TABLES T
                    ON T.TABSCHEMA = TABLE_SCHEMA(A.TABNAME, A.TABSCHEMA)
                    AND T.TABNAME = TABLE_NAME(A.TABNAME, A.TABSCHEMA)
            WHERE
                A.TYPE = 'A'
                AND T.STATUS = 'N'
            WITH UR""" % self.query_subst)
        for (
                schema,
                name,
                owner,
                system,
                created,
                desc,
                base_schema,
                base_table,
            ) in self.fetch_some(cursor):
            yield Alias(
                make_str(schema),
                make_str(name),
                make_str(owner),
                make_bool(system),
                make_datetime(created),
                make_str(desc),
                make_str(base_schema),
                make_str(base_table),
            )

    def get_view_dependencies(self):
        """Retrieves the details of view dependencies.

        Override this function to return a list of RelationDep tuples
        containing details of the relations upon which views depend (the tables
        and views that a view references in its query). RelationDep tuples
        contain the following named fields:

        schema       -- The schema of the view
        name         -- The name of the view
        dep_schema   -- The schema of the relation upon which the view depends
        dep_name     -- The name of the relation upon which the view depends
        """
        for row in super(InputPlugin, self).get_view_dependencies():
            yield row
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT
                RTRIM(T.TABSCHEMA) AS VIEWSCHEMA,
                RTRIM(T.TABNAME)   AS VIEWNAME,
                RTRIM(T.BSCHEMA)   AS DEPSCHEMA,
                RTRIM(T.BNAME)     AS DEPNAME
            FROM
                %(schema)s.TABDEP T
                INNER JOIN %(schema)s.VIEWS V
                    ON T.TABSCHEMA = V.VIEWSCHEMA
                    AND T.TABNAME = V.VIEWNAME
            WHERE
                T.DTYPE = 'V'
                AND T.BTYPE IN ('A', 'N', 'T', 'V')
                AND V.VALID = 'Y'
            WITH UR""" % self.query_subst)
        for (
                schema,
                name,
                depschema,
                depname,
            ) in self.fetch_some(cursor):
            yield RelationDep(
                make_str(schema),
                make_str(name),
                make_str(depschema),
                make_str(depname),
            )

    def get_indexes(self):
        """Retrieves the details of indexes stored in the database.

        Override this function to return a list of Index tuples containing
        details of the indexes defined in the database (including system
        indexes). Index tuples contain the following named fields:

        schema        -- The schema of the index
        name          -- The name of the index
        owner*        -- The name of the user who owns the index
        system        -- True if the index is system maintained (bool)
        created*      -- When the index was created (datetime)
        description*  -- Descriptive text
        table_schema  -- The schema of the table the index belongs to
        table_name    -- The name of the table the index belongs to
        tbspace       -- The name of the tablespace which contains the index
        last_stats*   -- When the index statistics were last updated (datetime)
        cardinality*  -- The approximate number of values in the index
        size*         -- The approximate size in bytes of the index
        unique        -- True if the index contains only unique values (bool)

        * Optional (can be None)
        """
        for row in super(InputPlugin, self).get_indexes():
            yield row
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT
                RTRIM(I.INDSCHEMA)                           AS INDSCHEMA,
                RTRIM(I.INDNAME)                             AS INDNAME,
                RTRIM(I.%(owner)s)                           AS OWNER,
                CASE USER_DEFINED
                    WHEN 0 THEN 'Y'
                    ELSE 'N'
                END                                          AS SYSTEM,
                CHAR(I.CREATE_TIME)                          AS CREATED,
                I.REMARKS                                    AS DESCRIPTION,
                RTRIM(I.TABSCHEMA)                           AS TABSCHEMA,
                RTRIM(I.TABNAME)                             AS TABNAME,
                COALESCE(RTRIM(TS.TBSPACE), 'NICKNAMESPACE') AS TBSPACE,
                CHAR(I.STATS_TIME)                           AS LASTSTATS,
                NULLIF(I.FULLKEYCARD, -1)                    AS CARD,
                BIGINT(NULLIF(I.NLEAF, -1)) * TS.PAGESIZE    AS SIZE,
                CASE I.UNIQUERULE
                    WHEN 'D' THEN 'N'
                    ELSE 'Y'
                END                                          AS UNIQUE
            FROM
                %(schema)s.INDEXES I
                INNER JOIN %(schema)s.TABLES T
                    ON I.TABSCHEMA = T.TABSCHEMA
                    AND I.TABNAME = T.TABNAME
                LEFT OUTER JOIN %(schema)s.TABLESPACES TS
                    ON I.TBSPACEID = TS.TBSPACEID
            WHERE
                T.STATUS = 'N'
            WITH UR""" % self.query_subst)
        for (
                schema,
                name,
                owner,
                system,
                created,
                desc,
                tabschema,
                tabname,
                tbspace,
                laststats,
                card,
                size,
                unique,
            ) in self.fetch_some(cursor):
            yield Index(
                make_str(schema),
                make_str(name),
                make_str(owner),
                make_bool(system),
                make_datetime(created),
                make_str(desc),
                make_str(tabschema),
                make_str(tabname),
                make_str(tbspace),
                make_datetime(laststats),
                make_int(card),
                make_int(size),
                make_bool(unique),
            )

    def get_index_cols(self):
        """Retrieves the list of columns belonging to indexes.

        Override this function to return a list of IndexCol tuples detailing
        the columns that belong to each index in the database (including system
        indexes).  IndexCol tuples contain the following named fields:

        index_schema -- The schema of the index
        index_name   -- The name of the index
        name         -- The name of the column
        order        -- The ordering of the column in the index:
                        'A' = Ascending
                        'D' = Descending
                        'I' = Include (not an index key)

        Note that the each tuple details one column belonging to an index. It
        is important that the list of tuples is in the order that each column
        is declared in an index.
        """
        for row in super(InputPlugin, self).get_index_cols():
            yield row
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT
                RTRIM(IC.INDSCHEMA) AS INDSCHEMA,
                RTRIM(IC.INDNAME)   AS INDNAME,
                RTRIM(IC.COLNAME)   AS COLNAME,
                IC.COLORDER         AS COLORDER
            FROM
                %(schema)s.INDEXCOLUSE IC
                INNER JOIN %(schema)s.INDEXES I
                    ON IC.INDSCHEMA = I.INDSCHEMA
                    AND IC.INDNAME = I.INDNAME
                INNER JOIN %(schema)s.TABLES T
                    ON I.TABSCHEMA = T.TABSCHEMA
                    AND I.TABNAME = T.TABNAME
            WHERE
                T.STATUS = 'N'
            ORDER BY
                IC.INDSCHEMA,
                IC.INDNAME,
                IC.COLSEQ
            WITH UR""" % self.query_subst)
        for (
                schema,
                name,
                colname,
                colorder,
            ) in self.fetch_some(cursor):
            yield IndexCol(
                make_str(schema),
                make_str(name),
                make_str(colname),
                make_str(colorder),
            )

    def get_relation_cols(self):
        """Retrieves the list of columns belonging to relations.

        Override this function to return a list of RelationCol tuples detailing
        the columns that belong to each relation (table, view, etc.) in the
        database (including system relations). RelationCol tuples contain the
        following named fields:

        relation_schema  -- The schema of the table
        relation_name    -- The name of the table
        name             -- The name of the column
        type_schema      -- The schema of the column's datatype
        type_name        -- The name of the column's datatype
        size*            -- The length of the column for character types, or the
                            numeric precision for decimal types (None if not a
                            character or decimal type)
        scale*           -- The maximum scale for decimal types (None if not a
                            decimal type)
        codepage*        -- The codepage of the column for character types (None
                            if not a character type)
        identity*        -- True if the column is an identity column (bool)
        nullable*        -- True if the column can store NULL (bool)
        cardinality*     -- The approximate number of unique values in the column
        null_card*       -- The approximate number of NULLs in the column
        generated        -- 'A' = Column is always generated
                            'D' = Column is generated by default
                            'N' = Column is not generated
        default*         -- If generated is 'N', the default value of the column
                            (expressed as SQL). Otherwise, the SQL expression that
                            generates the column's value (or default value). None
                            if the column has no default
        description*     -- Descriptive text

        Note that each tuple details one column belonging to a relation. It is
        important that the list of tuples is in the order that each column is
        declared in a relation.

        * Optional (can be None)
        """
        for row in super(InputPlugin, self).get_relation_cols():
            yield row
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT
                RTRIM(C.TABSCHEMA)                 AS TABSCHEMA,
                RTRIM(C.TABNAME)                   AS TABNAME,
                RTRIM(C.COLNAME)                   AS COLNAME,
                RTRIM(C.TYPESCHEMA)                AS TYPESCHEMA,
                RTRIM(C.TYPENAME)                  AS TYPENAME,
                NULLIF(C.LENGTH, 0)                AS SIZE,
                C.SCALE                            AS SCALE,
                -- XXX 0 is a legitimate codepage (e.g. FOR BIT DATA columns)
                NULLIF(C.CODEPAGE, 0)              AS CODEPAGE,
                CASE C.IDENTITY
                    WHEN 'Y' THEN 'Y'
                    ELSE 'N'
                END                                AS IDENTITY,
                C.NULLS                            AS NULLABLE,
                NULLIF(NULLIF(C.COLCARD, -1), -2)  AS CARDINALITY,
                NULLIF(C.NUMNULLS, -1)             AS NULLCARD,
                CASE C.GENERATED
                    WHEN 'A' THEN 'A'
                    WHEN 'D' THEN 'D'
                    ELSE 'N'
                END                                AS GENERATED,
                COALESCE(CASE C.GENERATED
                    WHEN '' THEN C.DEFAULT
                    ELSE C.TEXT
                END, '')                           AS DEFAULT,
                C.REMARKS                          AS DESCRIPTION
            FROM
                %(schema)s.COLUMNS C
                INNER JOIN %(schema)s.TABLES T
                    ON C.TABSCHEMA = T.TABSCHEMA
                    AND C.TABNAME = T.TABNAME
            WHERE
                C.HIDDEN <> 'S'
                AND T.TYPE IN ('A', 'N', 'T', 'V')
                AND T.STATUS = 'N'
            ORDER BY
                C.TABSCHEMA,
                C.TABNAME,
                C.COLNO
            WITH UR""" % self.query_subst)
        for (
                schema,
                name,
                colname,
                typeschema,
                typename,
                size,
                scale,
                codepage,
                identity,
                nullable,
                cardinality,
                nullcard,
                generated,
                default,
                desc,
            ) in self.fetch_some(cursor):
            if generated != 'N':
                default = re.sub(r'^\s*AS\s*', '', str(default))
            yield RelationCol(
                make_str(schema),
                make_str(name),
                make_str(colname),
                make_str(typeschema),
                make_str(typename),
                make_int(size),
                make_int(scale),
                make_int(codepage),
                make_bool(identity),
                make_bool(nullable),
                make_int(cardinality),
                make_int(nullcard),
                make_str(generated),
                make_str(default),
                make_str(desc),
            )

    def get_unique_keys(self):
        """Retrieves the details of unique keys stored in the database.

        Override this function to return a list of UniqueKey tuples containing
        details of the unique keys defined in the database. UniqueKey tuples
        contain the following named fields:

        table_schema  -- The schema of the table containing the key
        table_name    -- The name of the table containing the key
        name          -- The name of the key
        owner*        -- The name of the user who owns the key
        system        -- True if the key is system maintained (bool)
        created*      -- When the key was created (datetime)
        description*  -- Descriptive text
        primary       -- True if the unique key is also a primary key (bool)

        * Optional (can be None)
        """
        for row in super(InputPlugin, self).get_unique_keys():
            yield row
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT
                RTRIM(C.TABSCHEMA)      AS TABSCHEMA,
                RTRIM(C.TABNAME)        AS TABNAME,
                RTRIM(C.CONSTNAME)      AS KEYNAME,
                RTRIM(C.%(owner)s)      AS OWNER,
                CHAR('N')               AS SYSTEM,
                CAST(NULL AS TIMESTAMP) AS CREATED,
                C.REMARKS               AS DESCRIPTION,
                CASE C.TYPE
                    WHEN 'P' THEN 'Y'
                    ELSE 'N'
                END                     AS PRIMARY
            FROM
                %(schema)s.TABCONST C
                INNER JOIN %(schema)s.TABLES T
                    ON C.TABSCHEMA = T.TABSCHEMA
                    AND C.TABNAME = T.TABNAME
            WHERE
                C.TYPE IN ('U', 'P')
                AND T.STATUS = 'N'
            WITH UR""" % self.query_subst)
        for (
                schema,
                name,
                keyname,
                owner,
                system,
                created,
                desc,
                primary,
            ) in self.fetch_some(cursor):
            yield UniqueKey(
                make_str(schema),
                make_str(name),
                make_str(keyname),
                make_str(owner),
                make_bool(system),
                make_datetime(created),
                make_str(desc),
                make_bool(primary),
            )

    def get_unique_key_cols(self):
        """Retrieves the list of columns belonging to unique keys.

        Override this function to return a list of UniqueKeyCol tuples
        detailing the columns that belong to each unique key in the database.
        The tuples contain the following named fields:

        const_schema -- The schema of the table containing the key
        const_table  -- The name of the table containing the key
        const_name   -- The name of the key
        name         -- The name of the column
        """
        for row in super(InputPlugin, self).get_unique_key_cols():
            yield row
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT
                RTRIM(K.TABSCHEMA) AS TABSCHEMA,
                RTRIM(K.TABNAME)   AS TABNAME,
                RTRIM(K.CONSTNAME) AS KEYNAME,
                RTRIM(K.COLNAME)   AS COLNAME
            FROM
                %(schema)s.KEYCOLUSE K
                INNER JOIN %(schema)s.TABLES T
                    ON K.TABSCHEMA = T.TABSCHEMA
                    AND K.TABNAME = T.TABNAME
            WHERE
                T.STATUS = 'N'
            ORDER BY
                TABSCHEMA,
                TABNAME,
                CONSTNAME,
                COLSEQ
            WITH UR""" % self.query_subst)
        for (
                schema,
                name,
                keyname,
                colname
            ) in self.fetch_some(cursor):
            yield UniqueKeyCol(
                make_str(schema),
                make_str(name),
                make_str(keyname),
                make_str(colname),
            )

    def get_foreign_keys(self):
        """Retrieves the details of foreign keys stored in the database.

        Override this function to return a list of ForeignKey tuples containing
        details of the foreign keys defined in the database. ForeignKey tuples
        contain the following named fields:

        table_schema      -- The schema of the table containing the key
        table_name        -- The name of the table containing the key
        name              -- The name of the key
        owner*            -- The name of the user who owns the key
        system            -- True if the key is system maintained (bool)
        created*          -- When the key was created (datetime)
        description*      -- Descriptive text
        const_schema      -- The schema of the table the key references
        const_table       -- The name of the table the key references
        const_name        -- The name of the unique key that the key references
        delete_rule       -- The action to take on deletion of a parent key:
                             'A' = No action
                             'C' = Cascade
                             'N' = Set NULL
                             'R' = Restrict
        update_rule       -- The action to take on update of a parent key:
                             'A' = No action
                             'C' = Cascade
                             'N' = Set NULL
                             'R' = Restrict

        * Optional (can be None)
        """
        for row in super(InputPlugin, self).get_foreign_keys():
            yield row
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT
                RTRIM(C.TABSCHEMA)    AS TABSCHEMA,
                RTRIM(C.TABNAME)      AS TABNAME,
                RTRIM(C.CONSTNAME)    AS KEYNAME,
                RTRIM(C.%(owner)s)    AS OWNER,
                CHAR('N')             AS SYSTEM,
                CHAR(R.CREATE_TIME)   AS CREATED,
                C.REMARKS             AS DESCRIPTION,
                RTRIM(R.REFTABSCHEMA) AS REFTABSCHEMA,
                RTRIM(R.REFTABNAME)   AS REFTABNAME,
                RTRIM(R.REFKEYNAME)   AS REFKEYNAME,
                R.DELETERULE          AS DELETERULE,
                R.UPDATERULE          AS UPDATERULE
            FROM
                %(schema)s.TABCONST C
                INNER JOIN %(schema)s.TABLES TC
                    ON C.TABSCHEMA = TC.TABSCHEMA
                    AND C.TABNAME = TC.TABNAME
                INNER JOIN %(schema)s.REFERENCES R
                    ON C.TABSCHEMA = R.TABSCHEMA
                    AND C.TABNAME = R.TABNAME
                    AND C.CONSTNAME = R.CONSTNAME
                INNER JOIN %(schema)s.TABLES TR
                    ON R.REFTABSCHEMA = TR.TABSCHEMA
                    AND R.REFTABNAME = TR.TABNAME
            WHERE
                C.TYPE = 'F'
                AND TC.STATUS = 'N'
                AND TR.STATUS = 'N'
            WITH UR""" % self.query_subst)
        for (
                schema,
                name,
                keyname,
                owner,
                system,
                created,
                desc,
                refschema,
                refname,
                refkeyname,
                deleterule,
                updaterule,
            ) in self.fetch_some(cursor):
            yield ForeignKey(
                make_str(schema),
                make_str(name),
                make_str(keyname),
                make_str(owner),
                make_bool(system),
                make_datetime(created),
                make_str(desc),
                make_str(refschema),
                make_str(refname),
                make_str(refkeyname),
                make_str(deleterule),
                make_str(updaterule),
            )

    def get_foreign_key_cols(self):
        """Retrieves the list of columns belonging to foreign keys.

        Override this function to return a list of ForeignKeyCol tuples
        detailing the columns that belong to each foreign key in the database.
        ForeignKeyCol tuples contain the following named fields:

        const_schema -- The schema of the table containing the key
        const_table  -- The name of the table containing the key
        const_name   -- The name of the key
        name         -- The name of the column in the key
        ref_name     -- The name of the column that this column references in
                        the referenced key
        """
        for row in super(InputPlugin, self).get_foreign_key_cols():
            yield row
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT
                RTRIM(R.TABSCHEMA) AS TABSCHEMA,
                RTRIM(R.TABNAME)   AS TABNAME,
                RTRIM(R.CONSTNAME) AS KEYNAME,
                RTRIM(KF.COLNAME)  AS COLNAME,
                RTRIM(KP.COLNAME)  AS REFCOLNAME
            FROM
                %(schema)s.REFERENCES R
                INNER JOIN %(schema)s.TABLES TC
                    ON R.TABSCHEMA = TC.TABSCHEMA
                    AND R.TABNAME = TC.TABNAME
                INNER JOIN %(schema)s.TABLES TR
                    ON R.REFTABSCHEMA = TR.TABSCHEMA
                    AND R.REFTABNAME = TR.TABNAME
                INNER JOIN %(schema)s.KEYCOLUSE KF
                    ON R.TABSCHEMA = KF.TABSCHEMA
                    AND R.TABNAME = KF.TABNAME
                    AND R.CONSTNAME = KF.CONSTNAME
                INNER JOIN %(schema)s.KEYCOLUSE KP
                    ON R.REFTABSCHEMA = KP.TABSCHEMA
                    AND R.REFTABNAME = KP.TABNAME
                    AND R.REFKEYNAME = KP.CONSTNAME
            WHERE
                KF.COLSEQ = KP.COLSEQ
                AND TC.STATUS = 'N'
                AND TR.STATUS = 'N'
            ORDER BY
                R.TABSCHEMA,
                R.TABNAME,
                R.CONSTNAME,
                KF.COLSEQ
            WITH UR""" % self.query_subst)
        for (
                schema,
                name,
                keyname,
                colname,
                refcolname
            ) in self.fetch_some(cursor):
            yield ForeignKeyCol(
                make_str(schema),
                make_str(name),
                make_str(keyname),
                make_str(colname),
                make_str(refcolname),
            )

    def get_checks(self):
        """Retrieves the details of checks stored in the database.

        Override this function to return a list of Check tuples containing
        details of the checks defined in the database. Check tuples contain the
        following named fields:

        table_schema  -- The schema of the table containing the check
        table_name    -- The name of the table containing the check
        name          -- The name of the check
        owner*        -- The name of the user who owns the check
        system        -- True if the check is system maintained (bool)
        created*      -- When the check was created (datetime)
        description*  -- Descriptive text
        sql*          -- The SQL expression that the check enforces

        * Optional (can be None)
        """
        for row in super(InputPlugin, self).get_checks():
            yield row
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT
                RTRIM(TC.TABSCHEMA)   AS TABSCHEMA,
                RTRIM(TC.TABNAME)     AS TABNAME,
                RTRIM(TC.CONSTNAME)   AS CHECKNAME,
                RTRIM(TC.%(owner)s)   AS OWNER,
                CASE
                    WHEN C.TYPE IN ('A', 'S') THEN 'Y'
                    ELSE 'N'
                END                   AS SYSTEM,
                CHAR(C.CREATE_TIME)   AS CREATED,
                TC.REMARKS            AS DESCRIPTION,
                C.TEXT                AS SQL
            FROM
                %(schema)s.TABCONST TC
                INNER JOIN %(schema)s.TABLES T
                    ON TC.TABSCHEMA = T.TABSCHEMA
                    AND TC.TABNAME = T.TABNAME
                INNER JOIN %(schema)s.CHECKS C
                    ON TC.TABSCHEMA = C.TABSCHEMA
                    AND TC.TABNAME = C.TABNAME
                    AND TC.CONSTNAME = C.CONSTNAME
            WHERE
                TC.TYPE = 'K'
                AND T.STATUS = 'N'
            WITH UR""" % self.query_subst)
        for (
                schema,
                name,
                checkname,
                owner,
                system,
                created,
                desc,
                sql,
            ) in self.fetch_some(cursor):
            yield Check(
                make_str(schema),
                make_str(name),
                make_str(checkname),
                make_str(owner),
                make_bool(system),
                make_datetime(created),
                make_str(desc),
                make_str(sql),
            )

    def get_check_cols(self):
        """Retrieves the list of columns belonging to checks.

        Override this function to return a list of CheckCol tuples detailing
        the columns that are referenced by each check in the database. CheckCol
        tuples contain the following named fields:

        const_schema -- The schema of the table containing the check
        const_table  -- The name of the table containing the check
        const_name   -- The name of the check
        name         -- The name of the column
        """
        for row in super(InputPlugin, self).get_check_cols():
            yield row
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT
                RTRIM(C.TABSCHEMA) AS TABSCHEMA,
                RTRIM(C.TABNAME)   AS TABNAME,
                RTRIM(C.CONSTNAME) AS CHECKNAME,
                RTRIM(C.COLNAME)   AS COLNAME
            FROM
                %(schema)s.COLCHECKS C
                INNER JOIN %(schema)s.TABLES T
                    ON C.TABSCHEMA = T.TABSCHEMA
                    AND C.TABNAME = T.TABNAME
            WHERE
                T.STATUS = 'N'
            WITH UR""" % self.query_subst)
        for (
                schema,
                name,
                chkname,
                colname
            ) in self.fetch_some(cursor):
            yield CheckCol(
                make_str(schema),
                make_str(name),
                make_str(chkname),
                make_str(colname),
            )

    def get_functions(self):
        """Retrieves the details of functions stored in the database.

        Override this function to return a list of Function tuples containing
        details of the functions defined in the database (including system
        functions). Function tuples contain the following named fields:

        schema         -- The schema of the function
        specific       -- The unique name of the function in the schema
        name           -- The (potentially overloaded) name of the function
        owner*         -- The name of the user who owns the function
        system         -- True if the function is system maintained (bool)
        created*       -- When the function was created (datetime)
        description*   -- Descriptive text
        deterministic* -- True if the function is deterministic (bool)
        ext_action*    -- True if the function has an external action (affects
                          things outside the database) (bool)
        null_call*     -- True if the function is called on NULL input (bool)
        access*        -- 'N' if the function contains no SQL
                          'C' if the function contains database independent SQL
                          'R' if the function contains SQL that reads the db
                          'M' if the function contains SQL that modifies the db
        sql*           -- The SQL statement that defined the function
        func_type      -- The type of the function:
                          'C' = Column/aggregate function
                          'R' = Row function
                          'T' = Table function
                          'S' = Scalar function

        * Optional (can be None)
        """
        for row in super(InputPlugin, self).get_functions():
            yield row
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT
                RTRIM(ROUTINESCHEMA)         AS FUNCSCHEMA,
                RTRIM(SPECIFICNAME)          AS FUNCSPECNAME,
                RTRIM(ROUTINENAME)           AS FUNCNAME,
                RTRIM(%(owner)s)             AS OWNER,
                CASE
                    WHEN ORIGIN IN ('B', 'S', 'T') THEN 'Y'
                    ELSE 'N'
                END                          AS SYSTEM,
                CHAR(CREATE_TIME)            AS CREATED,
                REMARKS                      AS DESCRIPTION,
                DETERMINISTIC                AS DETERMINISTIC,
                EXTERNAL_ACTION              AS EXTACTION,
                NULLCALL                     AS NULLCALL,
                NULLIF(SQL_DATA_ACCESS, ' ') AS ACCESS,
                TEXT                         AS SQL,
                FUNCTIONTYPE                 AS FUNCTYPE
            FROM
                %(schema)s.ROUTINES
            WHERE
                ROUTINETYPE = 'F'
                AND VALID = 'Y'
            WITH UR""" % self.query_subst)
        for (
                schema,
                specname,
                name,
                owner,
                system,
                created,
                desc,
                deterministic,
                extaction,
                nullcall,
                access,
                sql,
                functype,
            ) in self.fetch_some(cursor):
            yield Function(
                make_str(schema),
                make_str(specname),
                make_str(name),
                make_str(owner),
                make_bool(system),
                make_datetime(created),
                make_str(desc),
                make_bool(deterministic),
                make_bool(extaction, true_value='E'),
                make_bool(nullcall),
                make_str(access),
                make_str(sql),
                make_str(functype),
            )

    def get_procedures(self):
        """Retrieves the details of stored procedures in the database.

        Override this function to return a list of Procedure tuples containing
        details of the procedures defined in the database (including system
        procedures). Procedure tuples contain the following named fields:

        schema         -- The schema of the procedure
        specific       -- The unique name of the procedure in the schema
        name           -- The (potentially overloaded) name of the procedure
        owner*         -- The name of the user who owns the procedure
        system         -- True if the procedure is system maintained (bool)
        created*       -- When the procedure was created (datetime)
        description*   -- Descriptive text
        deterministic* -- True if the procedure is deterministic (bool)
        ext_action*    -- True if the procedure has an external action (affects
                          things outside the database) (bool)
        null_call*     -- True if the procedure is called on NULL input
        access*        -- 'N' if the procedure contains no SQL
                          'C' if the procedure contains database independent SQL
                          'R' if the procedure contains SQL that reads the db
                          'M' if the procedure contains SQL that modifies the db
        sql*           -- The SQL statement that defined the procedure

        * Optional (can be None)
        """
        for row in super(InputPlugin, self).get_procedures():
            yield row
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT
                RTRIM(ROUTINESCHEMA)         AS PROCSCHEMA,
                RTRIM(SPECIFICNAME)          AS PROCSPECNAME,
                RTRIM(ROUTINENAME)           AS PROCNAME,
                RTRIM(%(owner)s)             AS OWNER,
                CASE
                    WHEN ORIGIN IN ('B', 'S', 'T') THEN 'Y'
                    ELSE 'N'
                END                          AS SYSTEM,
                CHAR(CREATE_TIME)            AS CREATED,
                REMARKS                      AS DESCRIPTION,
                DETERMINISTIC                AS DETERMINISTIC,
                EXTERNAL_ACTION              AS EXTACTION,
                NULLCALL                     AS NULLCALL,
                NULLIF(SQL_DATA_ACCESS, ' ') AS ACCESS,
                TEXT                         AS SQL
            FROM
                %(schema)s.ROUTINES
            WHERE
                ROUTINETYPE = 'P'
                AND VALID = 'Y'
            WITH UR""" % self.query_subst)
        for (
                schema,
                specname,
                name,
                owner,
                system,
                created,
                desc,
                deterministic,
                extaction,
                nullcall,
                access,
                sql
            ) in self.fetch_some(cursor):
            yield Procedure(
                make_str(schema),
                make_str(specname),
                make_str(name),
                make_str(owner),
                make_bool(system),
                make_datetime(created),
                make_str(desc),
                make_bool(deterministic),
                make_bool(extaction, true_value='E'),
                make_bool(nullcall),
                make_str(access),
                make_str(sql),
            )

    def get_routine_params(self):
        """Retrieves the list of parameters belonging to routines.

        Override this function to return a list of RoutineParam tuples
        detailing the parameters that are associated with each routine in the
        database. RoutineParam tuples contain the following named fields:

        routine_schema   -- The schema of the routine
        routine_specific -- The unique name of the routine in the schema
        param_name       -- The name of the parameter
        type_schema      -- The schema of the parameter's datatype
        type_name        -- The name of the parameter's datatype
        size*            -- The length of the parameter for character types, or
                            the numeric precision for decimal types (None if not
                            a character or decimal type)
        scale*           -- The maximum scale for decimal types (None if not a
                            decimal type)
        codepage*        -- The codepage of the parameter for character types
                            (None if not a character type)
        direction        -- 'I' = Input parameter
                            'O' = Output parameter
                            'B' = Input & output parameter
                            'R' = Return value/column
        description*     -- Descriptive text

        Note that the each tuple details one parameter belonging to a routine.
        It is important that the list of tuples is in the order that each
        parameter is declared in the routine.

        This is slightly complicated by the fact that the return column(s) of a
        routine are also considered parameters (see the direction field above).
        It does not matter if parameters and return columns are interspersed in
        the result provided that, taken separately, each set of parameters or
        columns is in the correct order.

        * Optional (can be None)
        """
        for row in super(InputPlugin, self).get_routine_params():
            yield row
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT
                RTRIM(P.ROUTINESCHEMA)          AS ROUTINESCHEMA,
                RTRIM(P.SPECIFICNAME)           AS ROUTINESPECNAME,
                RTRIM(COALESCE(P.PARMNAME, '')) AS PARMNAME,
                RTRIM(P.TYPESCHEMA)             AS TYPESCHEMA,
                RTRIM(P.TYPENAME)               AS TYPENAME,
                NULLIF(P.LENGTH, 0)             AS SIZE,
                P.SCALE                         AS SCALE,
                -- XXX 0 is a legitimate codepage (e.g. FOR BIT DATA types)
                NULLIF(P.CODEPAGE, 0)           AS CODEPAGE,
                CASE P.ROWTYPE
                    WHEN ' ' THEN 'I'
                    WHEN 'P' THEN 'I'
                    WHEN 'C' THEN 'R'
                    ELSE P.ROWTYPE
                END                             AS DIRECTION,
                P.REMARKS                       AS DESCRIPTION
            FROM
                %(schema)s.ROUTINEPARMS P
                INNER JOIN %(schema)s.ROUTINES R
                    ON P.ROUTINESCHEMA = R.ROUTINESCHEMA
                    AND P.SPECIFICNAME = R.SPECIFICNAME
            WHERE
                R.ROUTINETYPE IN ('F', 'P')
                AND R.VALID = 'Y'
            ORDER BY
                P.ROUTINESCHEMA,
                P.SPECIFICNAME,
                P.ORDINAL
            WITH UR""" % self.query_subst)
        for (
                schema,
                specname,
                parmname,
                typeschema,
                typename,
                size,
                scale,
                codepage,
                parmtype,
                desc
            ) in self.fetch_some(cursor):
            yield RoutineParam(
                make_str(schema),
                make_str(specname),
                make_str(parmname),
                make_str(typeschema),
                make_str(typename),
                make_int(size),
                make_int(scale),
                make_int(codepage),
                make_str(parmtype),
                make_str(desc),
            )

    def get_triggers(self):
        """Retrieves the details of table triggers in the database.

        Override this function to return a list of Trigger tuples containing
        details of the triggers defined in the database (including system
        triggers). Trigger tuples contain the following named fields:

        schema          -- The schema of the trigger
        name            -- The unique name of the trigger in the schema
        owner*          -- The name of the user who owns the trigger
        system          -- True if the trigger is system maintained (bool)
        created*        -- When the trigger was created (datetime)
        description*    -- Descriptive text
        relation_schema -- The schema of the relation that activates the trigger
        relation_name   -- The name of the relation that activates the trigger
        when            -- When the trigger is fired:
                           'A' = After the event
                           'B' = Before the event
                           'I' = Instead of the event
        event           -- What statement fires the trigger:
                           'I' = The trigger fires on INSERT
                           'U' = The trigger fires on UPDATE
                           'D' = The trigger fires on DELETE
        granularity     -- The granularity of trigger executions:
                           'R' = The trigger fires for each row affected
                           'S' = The trigger fires once per activating statement
        sql*            -- The SQL statement that defined the trigger

        * Optional (can be None)
        """
        for row in super(InputPlugin, self).get_triggers():
            yield row
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT
                RTRIM(TRIGSCHEMA)  AS TRIGSCHEMA,
                RTRIM(TRIGNAME)    AS TRIGNAME,
                RTRIM(%(owner)s)   AS OWNER,
                CHAR('N')          AS SYSTEM,
                CHAR(CREATE_TIME)  AS CREATED,
                REMARKS            AS DESCRIPTION,
                RTRIM(TABSCHEMA)   AS TABSCHEMA,
                RTRIM(TABNAME)     AS TABNAME,
                TRIGTIME           AS TRIGTIME,
                TRIGEVENT          AS TRIGEVENT,
                GRANULARITY        AS GRANULARITY,
                TEXT               AS SQL
            FROM
                %(schema)s.TRIGGERS
            WHERE
                VALID = 'Y'
            WITH UR""" % self.query_subst)
        for (
                schema,
                name,
                owner,
                system,
                created,
                desc,
                tabschema,
                tabname,
                trigtime,
                trigevent,
                granularity,
                sql,
            ) in self.fetch_some(cursor):
            yield Trigger(
                make_str(schema),
                make_str(name),
                make_str(owner),
                make_bool(system),
                make_datetime(created),
                make_str(desc),
                make_str(tabschema),
                make_str(tabname),
                make_str(trigtime),
                make_str(trigevent),
                make_str(granularity),
                make_str(sql),
            )

    def get_trigger_dependencies(self):
        """Retrieves the details of trigger dependencies.

        Override this function to return a list of TriggerDep tuples containing
        details of the relations upon which triggers depend (the tables that a
        trigger references in its body). TriggerDep tuples contain the
        following named fields:

        trig_schema  -- The schema of the trigger
        trig_name    -- The name of the trigger
        dep_schema   -- The schema of the relation upon which the trigger depends
        dep_name     -- The name of the relation upon which the trigger depends
        """
        for row in super(InputPlugin, self).get_trigger_dependencies():
            yield row
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT
                RTRIM(TD.TRIGSCHEMA) AS TRIGSCHEMA,
                RTRIM(TD.TRIGNAME)   AS TRIGNAME,
                RTRIM(TD.BSCHEMA)    AS DEPSCHEMA,
                RTRIM(TD.BNAME)      AS DEPNAME
            FROM
                %(schema)s.TRIGDEP TD
                INNER JOIN %(schema)s.TRIGGERS T
                    ON TD.TRIGSCHEMA = T.TRIGSCHEMA
                    AND TD.TRIGNAME = T.TRIGNAME
            WHERE
                TD.BTYPE IN ('A', 'N', 'T', 'V')
                AND T.VALID = 'Y'
                AND NOT (TD.BSCHEMA = T.TABSCHEMA AND TD.BNAME = T.TABNAME)
            WITH UR""" % self.query_subst)
        for (
                schema,
                name,
                depschema,
                depname
            ) in self.fetch_some(cursor):
            yield TriggerDep(
                make_str(schema),
                make_str(name),
                make_str(depschema),
                make_str(depname),
            )

    def get_tablespaces(self):
        """Retrieves the details of the tablespaces in the database.

        Override this function to return a list of Tablespace tuples containing
        details of the tablespaces defined in the database (including system
        tablespaces). Tablespace tuples contain the following named fields:

        tbspace       -- The tablespace name
        owner*        -- The name of the user who owns the tablespace
        system        -- True if the tablespace is system maintained (bool)
        created*      -- When the tablespace was created (datetime)
        description*  -- Descriptive text
        type*         -- The type of the tablespace as free text

        * Optional (can be None)
        """
        for row in super(InputPlugin, self).get_tablespaces():
            yield row
        cursor = self.connection.cursor()
        cursor.execute("""
            SELECT
                RTRIM(TBSPACE)    AS TBSPACE,
                RTRIM(%(owner)s)  AS OWNER,
                CASE TBSPACE
                    WHEN 'SYSCATSPACE' THEN 'Y'
                    WHEN 'SYSTOOLSPACE' THEN 'Y'
                    ELSE 'N'
                END               AS SYSTEM,
                CHAR(CREATE_TIME) AS CREATED,
                REMARKS           AS DESCRIPTION,
                CASE DATATYPE
                    WHEN 'A' THEN 'Regular'
                    WHEN 'L' THEN 'Long'
                    WHEN 'T' THEN 'System temporary'
                    WHEN 'U' THEN 'User temporary'
                    ELSE 'Unknown'
                END ||
                ' ' ||
                CASE TBSPACETYPE
                    WHEN 'D' THEN 'DMS'
                    WHEN 'S' THEN 'SMS'
                    ELSE 'unknown'
                END ||
                ' tablespace with ' ||
                RTRIM(CHAR(PAGESIZE / 1024)) ||
                'k page size' ||
                CASE DROP_RECOVERY
                    WHEN 'Y' THEN ' and drop recovery'
                    ELSE ''
                END               AS TYPE
            FROM
                %(schema)s.TABLESPACES

            UNION ALL

            SELECT
                'NICKNAMESPACE',
                'SYSIBM',
                'N',
                CHAR(CREATE_TIME),
                'Fake tablespace which contains all nicknames in the database',
                'Fake tablespace'
            FROM
                %(schema)s.TABLESPACES
            WHERE
                TBSPACE = 'SYSCATSPACE'
                AND EXISTS (
                    SELECT 1
                    FROM SYSCAT.TABLES
                    WHERE TYPE = 'N'
                    FETCH FIRST 1 ROW ONLY
                )
            WITH UR""" % self.query_subst)
        for (
                tbspace,
                owner,
                system,
                created,
                desc,
                tstype,
            ) in self.fetch_some(cursor):
            yield Tablespace(
                make_str(tbspace),
                make_str(owner),
                make_bool(system),
                make_datetime(created),
                make_str(desc),
                make_str(tstype),
            )

