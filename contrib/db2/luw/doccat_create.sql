-- vim: set noet sw=4 ts=4:

-------------------------------------------------------------------------------
-- Documentation Extensions for IBM DB2 for Linux/UNIX/Windows
--
-- FEATURES
-- ========
-- The extended capabilities of this system are as follows:
--
-- * Maximum length of comments is 32K chars instead of 254 chars
-- * Ability to comment on system routines (which for some bizarre reason
--   is not permitted normally in DB2)
-- * Ability to comment on routine parameters (the original SYSCAT.ROUTINEPARMS
--   view contains a REMARKS field, but there's no way to comment on routine
--   parameters using COMMENT ON)
-- * Easier to edit comments using standard SQL (e.g. to comment on several
--   overloaded routines one could comment on the first using INSERT..VALUES,
--   then add comments for the overloaded versions using INSERT..SELECT on
--   the first)
--
-- OVERVIEW
-- ========
-- This script creates various objects in a DB2 database for the purpose of
-- extending the documentation capabilities of DB2. Specifically, the following
-- objects are created:
--
-- DOCDATA schema
--   This schema contains several simple tables named after their counterparts
--   in the SYSCAT schema (e.g. COLUMNS, TABLES, TABCONST, etc). Each table
--   contains a unique key (e.g. TABSCHEMA, TABNAME, COLNAME for COLUMNS) plus
--   a CLOB(32K) REMARKS field which can hold considerably longer comments than
--   the typical VARCHAR(254) REMARKS fields in the SYSCAT schema.
--
-- DOCCAT schema
--   This schema duplicates all the views from SYSCAT schema, replacing the
--   REMARKS field (if the view has one) with the remarks from the
--   corresponding DOCDATA table (or the remarks from the original SYSCAT view
--   if the DOCDATA table doesn't contain an entry for the target object).
--   It also contains stored procedures for copying comments between the SYSCAT
--   and DOCCAT systems, and views which produce the source code for all
--   comments in the database.
--
-- USAGE
-- =====
-- To take advantage of the extended remarks, simply point any SYSCAT queries
-- at the DOCCAT schema instead (all views and fields have the same names, so
-- no other alterations should be necessary).
--
-- To document objects in your database, simply INSERT rows into the DOCDATA
-- tables instead of using COMMENT ON. You may find it easier to use instead of
-- the COMMENT statement (since you can duplicate comments by using INSERT ...
-- SELECT FROM ...)
--
-- To support applications which can only query SYSCAT, periodically update the
-- original comments in SYSCAT by using the DOCCAT.TO_SYSCAT procedure to
-- update the SYSCAT REMARKS columns.  Comments longer than 254 characters will
-- be truncated to 251 characters with ellipsis (...) appended to indicate
-- truncation has occurred.
--
-- INSTALLATION
-- ============
-- 1. Connect to the database you wish to install these features in
-- 2. Execute this file using bang (!) as the statement terminator
-- 3. Optionally CALL the DOCCAT.FROM_SYSCAT stored procedure (with
--    no arguments) to copy any existing comments to the DOCDATA tables
-- 4. Insert or update rows in the DOCDATA tables
--
-- NOTES
-- =====
-- The DOCCAT.FROM_SYSCAT stored procedure deletes the contents of the
-- DOCDATA tables prior to inserting data from the SYSCAT views. Therefore if
-- you have any extended comments (longer than 254 characters), or comments
-- which exist only in the DOCDATA tables, but not the SYSCAT views, you will
-- lose them.
-------------------------------------------------------------------------------

-------------------------------------------------------------------------------
-- Remove the content of the old DOCCAT and DOCDATA schemas
-------------------------------------------------------------------------------
CALL DOCCAT.UNINSTALL!
DROP SPECIFIC PROCEDURE DOCCAT.UNINSTALL!
DROP SCHEMA DOCCAT RESTRICT!
CREATE SCHEMA DOCDATA!
CREATE SCHEMA DOCCAT!

-------------------------------------------------------------------------------
-- Comments for DATATYPES
-------------------------------------------------------------------------------
CREATE TABLE DOCDATA.DATATYPES AS (
	SELECT
		TYPESCHEMA,
		TYPENAME,
		CAST(NULL AS CLOB(32K)) AS REMARKS
	FROM SYSCAT.DATATYPES
) WITH NO DATA!

CREATE UNIQUE INDEX DOCDATA.DATATYPES_PK
	ON DOCDATA.DATATYPES (TYPESCHEMA, TYPENAME)
	ALLOW REVERSE SCANS!

ALTER TABLE DOCDATA.DATATYPES
	ADD CONSTRAINT PK PRIMARY KEY (TYPESCHEMA, TYPENAME)!

-------------------------------------------------------------------------------
-- Comments for COLUMNS
-------------------------------------------------------------------------------
CREATE TABLE DOCDATA.COLUMNS AS (
	SELECT
		TABSCHEMA,
		TABNAME,
		COLNAME,
		CAST(NULL AS CLOB(32K)) AS REMARKS
	FROM SYSCAT.COLUMNS
) WITH NO DATA!

CREATE UNIQUE INDEX DOCDATA.COLUMNS_PK
	ON DOCDATA.COLUMNS (TABSCHEMA, TABNAME, COLNAME)
	ALLOW REVERSE SCANS!

ALTER TABLE DOCDATA.COLUMNS
	ADD CONSTRAINT PK PRIMARY KEY (TABSCHEMA, TABNAME, COLNAME)!

-------------------------------------------------------------------------------
-- Comments for CONSTRAINTS
-------------------------------------------------------------------------------
CREATE TABLE DOCDATA.TABCONST AS (
	SELECT
		TABSCHEMA,
		TABNAME,
		CONSTNAME,
		CAST(NULL AS CLOB(32K)) AS REMARKS
	FROM SYSCAT.TABCONST
) WITH NO DATA!

CREATE UNIQUE INDEX DOCDATA.TABCONST_PK
	ON DOCDATA.TABCONST (TABSCHEMA, TABNAME, CONSTNAME)
	ALLOW REVERSE SCANS!

ALTER TABLE DOCDATA.TABCONST
	ADD CONSTRAINT PK PRIMARY KEY (TABSCHEMA, TABNAME, CONSTNAME)!

-------------------------------------------------------------------------------
-- Comments for INDEXES
-------------------------------------------------------------------------------
CREATE TABLE DOCDATA.INDEXES AS (
	SELECT
		INDSCHEMA,
		INDNAME,
		CAST(NULL AS CLOB(32K)) AS REMARKS
	FROM SYSCAT.INDEXES
) WITH NO DATA!

CREATE UNIQUE INDEX DOCDATA.INDEXES_PK
	ON DOCDATA.INDEXES (INDSCHEMA, INDNAME)
	ALLOW REVERSE SCANS!

ALTER TABLE DOCDATA.INDEXES
	ADD CONSTRAINT PK PRIMARY KEY (INDSCHEMA, INDNAME)!

-------------------------------------------------------------------------------
-- Comments for ROUTINES
-------------------------------------------------------------------------------
CREATE TABLE DOCDATA.ROUTINES AS (
	SELECT
		ROUTINESCHEMA,
		SPECIFICNAME,
		CAST(NULL AS CLOB(32K)) AS REMARKS
	FROM SYSCAT.ROUTINES
) WITH NO DATA!

CREATE UNIQUE INDEX DOCDATA.ROUTINES_PK
	ON DOCDATA.ROUTINES (ROUTINESCHEMA, SPECIFICNAME)
	ALLOW REVERSE SCANS!

ALTER TABLE DOCDATA.ROUTINES
	ADD CONSTRAINT PK PRIMARY KEY (ROUTINESCHEMA, SPECIFICNAME)!

-------------------------------------------------------------------------------
-- Comments for ROUTINEPARMS
-------------------------------------------------------------------------------
CREATE TABLE DOCDATA.ROUTINEPARMS AS (
	SELECT
		COALESCE(ROUTINESCHEMA, '') AS ROUTINESCHEMA,
		COALESCE(SPECIFICNAME, '') AS SPECIFICNAME,
		PARMNAME,
		ROWTYPE,
		ORDINAL,
		CAST(NULL AS CLOB(32K)) AS REMARKS
	FROM SYSCAT.ROUTINEPARMS
) WITH NO DATA!

CREATE UNIQUE INDEX DOCDATA.ROUTINEPARMS_PK
	ON DOCDATA.ROUTINEPARMS (ROUTINESCHEMA, SPECIFICNAME, ROWTYPE, ORDINAL)
	INCLUDE (PARMNAME)
	ALLOW REVERSE SCANS!

ALTER TABLE DOCDATA.ROUTINEPARMS
	ADD CONSTRAINT PK PRIMARY KEY (ROUTINESCHEMA, SPECIFICNAME, ROWTYPE, ORDINAL)
	ADD CONSTRAINT ROWTYPE_CK CHECK (ROWTYPE IN ('B', 'C', 'O', 'P', 'R'))
	ADD CONSTRAINT ORDINAL_CK CHECK (ORDINAL >= 0)!

-------------------------------------------------------------------------------
-- Comments for SCHEMATA
-------------------------------------------------------------------------------
CREATE TABLE DOCDATA.SCHEMATA AS (
	SELECT
		SCHEMANAME,
		CAST(NULL AS CLOB(32K)) AS REMARKS
	FROM SYSCAT.SCHEMATA
) WITH NO DATA!

CREATE UNIQUE INDEX DOCDATA.SCHEMATA_PK
	ON DOCDATA.SCHEMATA (SCHEMANAME)
	ALLOW REVERSE SCANS!

ALTER TABLE DOCDATA.SCHEMATA
	ADD CONSTRAINT PK PRIMARY KEY (SCHEMANAME)!

-------------------------------------------------------------------------------
-- Comments for TABLES
-------------------------------------------------------------------------------
CREATE TABLE DOCDATA.TABLES AS (
	SELECT
		TABSCHEMA,
		TABNAME,
		CAST(NULL AS CLOB(32K)) AS REMARKS
	FROM SYSCAT.TABLES
) WITH NO DATA!

CREATE UNIQUE INDEX DOCDATA.TABLES_PK
	ON DOCDATA.TABLES (TABSCHEMA, TABNAME)
	ALLOW REVERSE SCANS!

ALTER TABLE DOCDATA.TABLES
	ADD CONSTRAINT PK PRIMARY KEY (TABSCHEMA, TABNAME)!

-------------------------------------------------------------------------------
-- Comments for TRIGGERS
-------------------------------------------------------------------------------
CREATE TABLE DOCDATA.TRIGGERS AS (
	SELECT
		TRIGSCHEMA,
		TRIGNAME,
		CAST(NULL AS CLOB(32K)) AS REMARKS
	FROM SYSCAT.TRIGGERS
) WITH NO DATA!

CREATE UNIQUE INDEX DOCDATA.TRIGGERS_PK
	ON DOCDATA.TRIGGERS (TRIGSCHEMA, TRIGNAME)
	ALLOW REVERSE SCANS!

ALTER TABLE DOCDATA.TRIGGERS
	ADD CONSTRAINT PK PRIMARY KEY (TRIGSCHEMA, TRIGNAME)!

-------------------------------------------------------------------------------
-- Comments for TABLESPACES
-------------------------------------------------------------------------------
CREATE TABLE DOCDATA.TABLESPACES AS (
	SELECT
		TBSPACE,
		CAST(NULL AS CLOB(32K)) AS REMARKS
	FROM SYSCAT.TABLESPACES
) WITH NO DATA!

CREATE UNIQUE INDEX DOCDATA.TABLESPACES_PK
	ON DOCDATA.TABLESPACES (TBSPACE)
	ALLOW REVERSE SCANS!

ALTER TABLE DOCDATA.TABLESPACES
	ADD CONSTRAINT PK PRIMARY KEY (TBSPACE)!

-------------------------------------------------------------------------------
-- Create utility procedures
-------------------------------------------------------------------------------

CREATE VIEW DOCCAT.TO_COMMENTS (SQL) AS
	WITH DATA (TYPE, ID, REMARKS) AS (
		SELECT
			'TABLESPACE',
			'"' || D.TBSPACE || '"',
			D.REMARKS
		FROM
			SYSCAT.TABLESPACES S
			INNER JOIN DOCDATA.TABLESPACES D
				ON S.TBSPACE = D.TBSPACE

		UNION ALL

		SELECT
			'SCHEMA',
			'"' || D.SCHEMANAME || '"',
			D.REMARKS
		FROM
			SYSCAT.SCHEMATA S
			INNER JOIN DOCDATA.SCHEMATA D
				ON S.SCHEMANAME = D.SCHEMANAME

		UNION ALL

		SELECT
			'TABLE',
			'"' || D.TABSCHEMA || '"."' || D.TABNAME || '"',
			D.REMARKS
		FROM
			SYSCAT.TABLES S
			INNER JOIN DOCDATA.TABLES D
				ON S.TABSCHEMA = D.TABSCHEMA
				AND S.TABNAME = D.TABNAME

		UNION ALL

		SELECT
			'COLUMN',
			'"' || D.TABSCHEMA || '"."' || D.TABNAME || '"."' || D.COLNAME || '"',
			D.REMARKS
		FROM
			SYSCAT.COLUMNS S
			INNER JOIN DOCDATA.COLUMNS D
				ON S.TABSCHEMA = D.TABSCHEMA
				AND S.TABNAME = D.TABNAME
				AND S.COLNAME = D.COLNAME

		UNION ALL

		SELECT
			'CONSTRAINT',
			'"' || D.TABSCHEMA || '"."' || D.TABNAME || '"."' || D.CONSTNAME || '"',
			D.REMARKS
		FROM
			SYSCAT.TABCONST S
			INNER JOIN DOCDATA.TABCONST D
				ON S.TABSCHEMA = D.TABSCHEMA
				AND S.TABNAME = D.TABNAME
				AND S.CONSTNAME = D.CONSTNAME

		UNION ALL

		SELECT
			'INDEX',
			'"' || D.INDSCHEMA || '"."' || D.INDNAME || '"',
			D.REMARKS
		FROM
			SYSCAT.INDEXES S
			INNER JOIN DOCDATA.INDEXES D
				ON S.INDSCHEMA = D.INDSCHEMA
				AND S.INDNAME = D.INDNAME

		UNION ALL

		SELECT
			'TRIGGER',
			'"' || D.TRIGSCHEMA || '"."' || D.TRIGNAME || '"',
			D.REMARKS
		FROM
			SYSCAT.TRIGGERS S
			INNER JOIN DOCDATA.TRIGGERS D
				ON S.TRIGSCHEMA = D.TRIGSCHEMA
				AND S.TRIGNAME = D.TRIGNAME

		UNION ALL

		SELECT
			CASE WHEN S.ROUTINETYPE = 'P'
				THEN 'SPECIFIC PROCEDURE'
				ELSE 'SPECIFIC FUNCTION'
			END,
			'"' || D.ROUTINESCHEMA || '"."' || D.SPECIFICNAME || '"',
			D.REMARKS
		FROM
			SYSCAT.ROUTINES S
			INNER JOIN DOCDATA.ROUTINES D
				ON S.ROUTINESCHEMA = D.ROUTINESCHEMA
				AND S.SPECIFICNAME = D.SPECIFICNAME

		UNION ALL

		SELECT
			'TYPE',
			'"' || D.TYPESCHEMA || '"."' || D.TYPENAME || '"',
			D.REMARKS
		FROM
			SYSCAT.DATATYPES S
			INNER JOIN DOCDATA.DATATYPES D
				ON S.TYPESCHEMA = D.TYPESCHEMA
				AND S.TYPENAME = D.TYPENAME
	)
	SELECT
		'COMMENT ON ' || TYPE || ' ' || ID || ' IS ''' ||
			REPLACE(CAST(CASE WHEN LENGTH(REMARKS) <= 254
				THEN REMARKS
				ELSE LEFT(REMARKS, 251) || '...'
			END AS VARCHAR(254)), '''', '''''') || ''''
	FROM
		DATA
	WHERE
		REMARKS IS NOT NULL!

CREATE PROCEDURE DOCCAT.COPY_ROUTINE(
	OLD_SCHEMA VARCHAR(128),
	OLD_SPECIFICNAME VARCHAR(128),
	NEW_SPECIFICNAME VARCHAR(128)
)
	SPECIFIC COPY_ROUTINE
	MODIFIES SQL DATA
	NO EXTERNAL ACTION
BEGIN ATOMIC
	DELETE FROM DOCDATA.ROUTINES
		WHERE
			ROUTINESCHEMA = OLD_SCHEMA
			AND SPECIFICNAME = NEW_SPECIFICNAME;
	INSERT INTO DOCDATA.ROUTINES (ROUTINESCHEMA, SPECIFICNAME, REMARKS)
		SELECT
			OLD_SCHEMA,
			NEW_SPECIFICNAME,
			REMARKS
		FROM
			DOCDATA.ROUTINES
		WHERE
			ROUTINESCHEMA = OLD_SCHEMA
			AND SPECIFICNAME = OLD_SPECIFICNAME;
END!

CREATE PROCEDURE DOCCAT.COPY_ROUTINE_PARMS(
	OLD_SCHEMA VARCHAR(128),
	OLD_SPECIFICNAME VARCHAR(128),
	NEW_SPECIFICNAME VARCHAR(128)
)
	SPECIFIC COPY_ROUTINEPARMS
	MODIFIES SQL DATA
	NO EXTERNAL ACTION
BEGIN ATOMIC
	DELETE FROM DOCDATA.ROUTINEPARMS
		WHERE
			ROUTINESCHEMA = OLD_SCHEMA
			AND SPECIFICNAME = NEW_SPECIFICNAME;
	INSERT INTO DOCDATA.ROUTINEPARMS
		(ROUTINESCHEMA, SPECIFICNAME, ROWTYPE, ORDINAL, PARMNAME, REMARKS)
		SELECT
			OLD_SCHEMA,
			NEW_SPECIFICNAME,
			ROWTYPE,
			ORDINAL,
			PARMNAME,
			REMARKS
		FROM
			DOCDATA.ROUTINEPARMS
		WHERE
			ROUTINESCHEMA = OLD_SCHEMA
			AND SPECIFICNAME = OLD_SPECIFICNAME;
END!

CREATE PROCEDURE DOCCAT.TO_SYSCAT()
	SPECIFIC TO_SYSCAT
	MODIFIES SQL DATA
	NO EXTERNAL ACTION
	NOT DETERMINISTIC
	LANGUAGE SQL
BEGIN ATOMIC
	FOR D AS
		SELECT SQL FROM DOCCAT.TO_COMMENTS
	DO
		EXECUTE IMMEDIATE D.SQL;
	END FOR;
END!

CREATE PROCEDURE DOCCAT.FROM_SYSCAT()
	SPECIFIC FROM_SYSCAT
	MODIFIES SQL DATA
	NO EXTERNAL ACTION
	NOT DETERMINISTIC
	LANGUAGE SQL
BEGIN ATOMIC
	DELETE FROM DOCDATA.DATATYPES;
	INSERT INTO DOCDATA.DATATYPES (TYPESCHEMA, TYPENAME, REMARKS)
		SELECT TYPESCHEMA, TYPENAME, REMARKS
		FROM SYSCAT.DATATYPES
		WHERE COALESCE(REMARKS, '') <> '';
	DELETE FROM DOCDATA.COLUMNS;
	INSERT INTO DOCDATA.COLUMNS (TABSCHEMA, TABNAME, COLNAME, REMARKS)
		SELECT TABSCHEMA, TABNAME, COLNAME, REMARKS
		FROM SYSCAT.COLUMNS
		WHERE COALESCE(REMARKS, '') <> '';
	DELETE FROM DOCDATA.TABCONST;
	INSERT INTO DOCDATA.TABCONST (TABSCHEMA, TABNAME, CONSTNAME, REMARKS)
		SELECT TABSCHEMA, TABNAME, CONSTNAME, REMARKS
		FROM SYSCAT.TABCONST
		WHERE COALESCE(REMARKS, '') <> '';
	DELETE FROM DOCDATA.INDEXES;
	INSERT INTO DOCDATA.INDEXES (INDSCHEMA, INDNAME, REMARKS)
		SELECT INDSCHEMA, INDNAME, REMARKS
		FROM SYSCAT.INDEXES
		WHERE COALESCE(REMARKS, '') <> '';
	DELETE FROM DOCDATA.TRIGGERS;
	INSERT INTO DOCDATA.TRIGGERS (TRIGSCHEMA, TRIGNAME, REMARKS)
		SELECT TRIGSCHEMA, TRIGNAME, REMARKS
		FROM SYSCAT.TRIGGERS
		WHERE COALESCE(REMARKS, '') <> '';
	DELETE FROM DOCDATA.ROUTINES;
	INSERT INTO DOCDATA.ROUTINES (ROUTINESCHEMA, SPECIFICNAME, REMARKS)
		SELECT ROUTINESCHEMA, SPECIFICNAME, REMARKS
		FROM SYSCAT.ROUTINES
		WHERE COALESCE(REMARKS, '') <> '';
	DELETE FROM DOCDATA.ROUTINEPARMS;
	INSERT INTO DOCDATA.ROUTINEPARMS (ROUTINESCHEMA, SPECIFICNAME, ROWTYPE, ORDINAL, PARMNAME, REMARKS)
		SELECT
			ROUTINESCHEMA,
			SPECIFICNAME,
			ROWTYPE,
			ORDINAL,
			CASE WHEN PARMNAME IS NULL OR PARMNAME = ''
				THEN RTRIM('P' || CHAR(ORDINAL))
				ELSE PARMNAME
			END,
			REMARKS
		FROM SYSCAT.ROUTINEPARMS
		WHERE COALESCE(REMARKS, '') <> '';
	DELETE FROM DOCDATA.TABLES;
	INSERT INTO DOCDATA.TABLES (TABSCHEMA, TABNAME, REMARKS)
		SELECT TABSCHEMA, TABNAME, REMARKS
		FROM SYSCAT.TABLES
		WHERE COALESCE(REMARKS, '') <> '';
	DELETE FROM DOCDATA.SCHEMATA;
	INSERT INTO DOCDATA.SCHEMATA (SCHEMANAME, REMARKS)
		SELECT SCHEMANAME, REMARKS
		FROM SYSCAT.SCHEMATA
		WHERE COALESCE(REMARKS, '') <> '';
	DELETE FROM DOCDATA.TABLESPACES;
	INSERT INTO DOCDATA.TABLESPACES (TBSPACE, REMARKS)
		SELECT TBSPACE, REMARKS
		FROM SYSCAT.TABLESPACES
		WHERE COALESCE(REMARKS, '') <> '';
END!

-------------------------------------------------------------------------------
-- Create installation / uninstallation procedures.
--
-- NOTE: These should only be called by this script (or future) scripts for
-- installing / upgrading / removing the DOCCAT system
-------------------------------------------------------------------------------

CREATE PROCEDURE DOCCAT.INSTALL_VIEW(ATABLE VARCHAR(128))
	SPECIFIC INSTALL_VIEW
	MODIFIES SQL DATA
	NO EXTERNAL ACTION
	NOT DETERMINISTIC
	LANGUAGE SQL
BEGIN ATOMIC
	DECLARE DDL VARCHAR(8192) DEFAULT '';
	FOR C AS
		SELECT
			CASE COLNAME WHEN 'REMARKS'
				THEN 'COALESCE(D.REMARKS,S.REMARKS) AS REMARKS'
				ELSE 'S.' || RTRIM(COLNAME)
			END AS COLNAME
		FROM SYSCAT.COLUMNS
		WHERE TABSCHEMA = 'SYSCAT'
		AND TABNAME = ATABLE
		ORDER BY COLNO
	DO
		SET DDL = DDL || C.COLNAME || ',';
	END FOR;
	SET DDL = 'CREATE VIEW DOCCAT.' || RTRIM(ATABLE) || ' AS ' ||
		'SELECT ' || LEFT(DDL, LENGTH(DDL) - 1) || ' ' ||
		'FROM SYSCAT.' || RTRIM(ATABLE) || ' S ' ||
		'LEFT JOIN DOCDATA.' || RTRIM(ATABLE) || ' D';
	FOR C AS
		SELECT KEYSEQ, COLNAME
		FROM SYSCAT.COLUMNS
		WHERE TABSCHEMA = 'DOCDATA'
		AND TABNAME = ATABLE
		AND KEYSEQ IS NOT NULL
		ORDER BY KEYSEQ
	DO
		SET DDL = DDL || CASE KEYSEQ WHEN 1 THEN ' ON ' ELSE ' AND ' END ||
			'S.' || RTRIM(C.COLNAME) || '=D.' || RTRIM(C.COLNAME);
	END FOR;
	EXECUTE IMMEDIATE DDL;
END!

CREATE PROCEDURE DOCCAT.INSTALL_TRIGGER(ATABLE VARCHAR(128))
	SPECIFIC INSTALL_TRIGGER
	MODIFIES SQL DATA
	NO EXTERNAL ACTION
	NOT DETERMINISTIC
	LANGUAGE SQL
BEGIN ATOMIC
	DECLARE DDL VARCHAR(8192) DEFAULT '';
	DECLARE WHERE_KEY VARCHAR(1024) DEFAULT '';
	DECLARE INSERT_COLS VARCHAR(1024) DEFAULT '';
	DECLARE INSERT_VALS VARCHAR(1024) DEFAULT '';
	FOR C AS
		SELECT KEYSEQ, COLNAME
		FROM SYSCAT.COLUMNS
		WHERE TABSCHEMA = 'DOCDATA'
		AND TABNAME = ATABLE
		AND KEYSEQ IS NOT NULL
		ORDER BY KEYSEQ
	DO
		SET WHERE_KEY = WHERE_KEY || CASE KEYSEQ WHEN 1 THEN ' WHERE ' ELSE ' AND ' END ||
			RTRIM(COLNAME) || '=O.' || RTRIM(COLNAME);
		SET INSERT_COLS = INSERT_COLS || CASE KEYSEQ WHEN 1 THEN '' ELSE ',' END || RTRIM(COLNAME);
		SET INSERT_VALS = INSERT_VALS || CASE KEYSEQ WHEN 1 THEN '' ELSE ',' END || 'O.' || RTRIM(COLNAME);
	END FOR;
	SET INSERT_COLS = '(' || INSERT_COLS || ',REMARKS)';
	SET INSERT_VALS = '(' || INSERT_VALS || ',N.REMARKS)';
	SET DDL =
		'CREATE TRIGGER DOCCAT.' || ATABLE || ' ' ||
			'INSTEAD OF UPDATE ON DOCCAT.' || ATABLE || ' ' ||
			'REFERENCING OLD AS O NEW AS N ' ||
			'FOR EACH ROW ' ||
		'BEGIN ATOMIC ' ||
			'IF 0 = (SELECT COUNT(*) FROM DOCDATA.' || ATABLE || WHERE_KEY || ') THEN ' ||
				'IF N.REMARKS IS NOT NULL THEN ' ||
					'INSERT INTO DOCDATA.' || ATABLE || INSERT_COLS || ' ' ||
					'VALUES ' || INSERT_VALS || '; ' ||
				'END IF; ' ||
			'ELSE ' ||
				'IF N.REMARKS IS NULL THEN ' ||
					'DELETE FROM DOCDATA.' || ATABLE || WHERE_KEY || '; ' ||
				'ELSE ' ||
					'UPDATE DOCDATA.' || ATABLE || ' SET REMARKS=N.REMARKS' || WHERE_KEY || '; ' ||
				'END IF; ' ||
			'END IF; ' ||
		'END';
	EXECUTE IMMEDIATE DDL;
END!

CREATE PROCEDURE DOCCAT.INSTALL()
	SPECIFIC INSTALL
	MODIFIES SQL DATA
	NO EXTERNAL ACTION
	NOT DETERMINISTIC
	LANGUAGE SQL
BEGIN ATOMIC
	DECLARE DDL VARCHAR(1024) DEFAULT '';
	FOR D AS
		SELECT TABNAME
		FROM SYSCAT.TABLES
		WHERE TABSCHEMA = 'SYSCAT'
	DO
		IF 1 = (SELECT 1 FROM SYSCAT.TABLES WHERE TABSCHEMA = 'DOCDATA' AND TABNAME = D.TABNAME) THEN
			CALL DOCCAT.INSTALL_VIEW(D.TABNAME);
			CALL DOCCAT.INSTALL_TRIGGER(D.TABNAME);
		ELSE
			SET DDL = 'CREATE ALIAS DOCCAT.' || RTRIM(D.TABNAME) || ' FOR SYSCAT.' || RTRIM(D.TABNAME);
			EXECUTE IMMEDIATE DDL;
		END IF;
	END FOR;
END!

CREATE PROCEDURE DOCCAT.UNINSTALL()
	SPECIFIC UNINSTALL
	MODIFIES SQL DATA
	NO EXTERNAL ACTION
	NOT DETERMINISTIC
	LANGUAGE SQL
BEGIN ATOMIC
	FOR D AS
		SELECT 1 AS ORD, 'DROP ALIAS DOCCAT.' || TABNAME AS DDL
		FROM SYSCAT.TABLES
		WHERE TABSCHEMA = 'DOCCAT'
		AND TYPE = 'A'
		UNION ALL
		SELECT 2 AS ORD, 'DROP TRIGGER DOCCAT.' || TRIGNAME AS DDL
		FROM SYSCAT.TRIGGERS
		WHERE TRIGSCHEMA = 'DOCCAT'
		UNION ALL
		SELECT 3 AS ORD, 'DROP VIEW DOCCAT.' || TABNAME AS DDL
		FROM SYSCAT.TABLES
		WHERE TABSCHEMA = 'DOCCAT'
		AND TYPE = 'V'
		UNION ALL
		SELECT 4 AS ORD, 'DROP SPECIFIC PROCEDURE DOCCAT.' || ROUTINENAME AS DDL
		FROM SYSCAT.ROUTINES
		WHERE ROUTINESCHEMA = 'DOCCAT'
		AND ROUTINENAME <> 'UNINSTALL'
		AND ROUTINETYPE = 'P'
		UNION ALL
		SELECT 5 AS ORD, 'DROP TABLE DOCDATA.' || TABNAME AS DDL
		FROM SYSCAT.TABLES
		WHERE TABSCHEMA = 'DOCDATA'
		AND TYPE = 'T'
		UNION ALL
		SELECT 6 AS ORD, 'DROP SCHEMA ' || SCHEMANAME || ' RESTRICT' AS DDL
		FROM SYSCAT.SCHEMATA
		WHERE SCHEMANAME IN ('DOCDATA', 'DOCTOOLS')
		ORDER BY ORD
	DO
		EXECUTE IMMEDIATE D.DDL;
	END FOR;
END!

-------------------------------------------------------------------------------
-- Create replacement SYSCAT views in DOCCAT
-------------------------------------------------------------------------------

CALL DOCCAT.INSTALL()!

-------------------------------------------------------------------------------
-- COMMIT everything and finish
-------------------------------------------------------------------------------
COMMIT!
