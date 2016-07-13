#! /usr/bin/env python
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# IndigoSql by RogueProeliator <adam.d.ashe@gmail.com>
#	This file provides access to a SQL database in a standard method, be it in
#	SQLList or PostGRE format.
# 
#	Much of this file was adapted from Perceptive Automation's SQL Logger plugin and used
#	with permission of the authors. Therefore, portions of this code are governed by their
#	copyright, found below. As such, redistribution of this software in any form is not
#	permitted without permission from all parties.
#
# 	################### ORIGINAL COPYRIGHT ###################
# 	Copyright (c) 2012, Perceptive Automation, LLC. All rights reserved.
# 	http://www.perceptiveautomation.com
#
# 	Redistribution of this source file, its binary forms, and images are not allowed.
#
# 	THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY
# 	EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES
# 	OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.
#
# 	IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT,
# 	INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
# 	NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
#
# 	LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# 	THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# 	NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN
# 	IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
# 	##########################################################
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////


#/////////////////////////////////////////////////////////////////////////////////////////
# Python imports
#/////////////////////////////////////////////////////////////////////////////////////////
import datetime
import os
import re
import socket
import sys
import time
import ConfigParser
from errno import EWOULDBLOCK, EINTR, EMSGSIZE, ECONNREFUSED, EAGAIN


#/////////////////////////////////////////////////////////////////////////////////////////
# Constants and configuration variables
#/////////////////////////////////////////////////////////////////////////////////////////
kDbType_sqlite = 0
kDbType_postgres = 1
kAutoIncrKey_sqlite = u"INTEGER PRIMARY KEY"
kAutoIncrKey_postgres = u"SERIAL PRIMARY KEY"
kDbConnectTimeout = 8


#/////////////////////////////////////////////////////////////////////////////////////////
# SQLLite database type conversion routines
#/////////////////////////////////////////////////////////////////////////////////////////
def adapt_boolean(val):
	if val:
		return "True"
	else:
		return "False"

def convert_boolean(valStr):
	if str(valStr) == "True":
		return bool(True)
	elif str(valStr) == "False":
		return bool(False)
	else:
		raise ValueError, "Unknown value of bool attribute '%s'" % valStr

def nopDebugLog(unusedMsg):
	pass


#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# IndigoSql
#	Base class for database access which allows for a standard interface to the different
#	database types supported by the SQL Logger
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
class IndigoSql:

	#/////////////////////////////////////////////////////////////////////////////////////
	# Class construction and destruction methods
	#/////////////////////////////////////////////////////////////////////////////////////
	def __init__(self, sqlType, sleepFunc, logFunc, debugLogFunc):
		self.sqlType = sqlType
		if self.sqlType == kDbType_sqlite:
			self.sqlAutoIncrKey = kAutoIncrKey_sqlite
		elif self.sqlType == kDbType_postgres:
			self.sqlAutoIncrKey = kAutoIncrKey_postgres
		else:
			raise Exception('databaseType specified not valid (select sqlite or postgres)')

		self._Sleep = sleepFunc
		self._Log = logFunc
		self._DebugLog = debugLogFunc
		if not self._DebugLog:
			self._DebugLog = nopDebugLog

		self.sqlConn = None
		self.sqlConnGood = False
		self.sqlCursor = None


	#/////////////////////////////////////////////////////////////////////////////////////
	# Property-access style functions
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# Returns a boolean indicating if the database connection is up-and-running
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def IsSqlConnectionGood(self):
		return self.sqlConnGood

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# Allows quickly determining if this is a PostGRE database type
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def IsTypePostgres(self):
		return self.sqlType == kDbType_postgres

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# Allows quickly determining if this is a SQLLite database type
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def IsTypeSqlite(self):
		return self.sqlType == kDbType_sqlite


	#/////////////////////////////////////////////////////////////////////////////////////
	# Database connection routines
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This will "safely" shut down the database connection and connected data
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def CloseSqlConnection(self):
		if self.sqlCursor:
			self.sqlCursor.close()
			self.sqlCursor = None
		if self.sqlConn:
			self.sqlConn.close()
			self.sqlConn = None


	#/////////////////////////////////////////////////////////////////////////////////////
	# Database structure access routines
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will return a list of table names that exist within the SQL logger
	# database
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def GetAllTableNames(self):
		# PostgreSQL doesn't have IF NOT EXISTS when creating tables, so we have to query the schema.
		if not self.sqlConn or not self.sqlCursor:
			raise Exception('not connected to database')

		tableNames = []
		if self.sqlType == kDbType_sqlite:
			self.sqlCursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
			for nameObj in self.sqlCursor.fetchall():
				tableNames.append(nameObj[0])
		elif self.sqlType == kDbType_postgres:
			self.sqlCursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
			for nameObj in self.sqlCursor.fetchall():
				tableNames.append(nameObj[0])
		return tableNames

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine check to see if a table by the given name already exists in the DB
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def TableExists(self, tableName):
		# PostgreSQL doesn't have IF NOT EXISTS when creating tables, so we have to query the schema.
		if not self.sqlConn or not self.sqlCursor:
			raise Exception('not connected to database')

		if self.sqlType == kDbType_sqlite:
			self.sqlCursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (tableName,))
			return len(self.sqlCursor.fetchall()) == 1
		elif self.sqlType == kDbType_postgres:
			self.sqlCursor.execute("SELECT * FROM information_schema.tables WHERE table_schema='public' AND table_name=%s;", (tableName,))
			return self.sqlCursor.rowcount == 1
		return False

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will create a dictionary of the column names and types defined for
	# the given table name
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def GetTableColumnNamesAndTypes(self, tableName):
		if not self.sqlConn or not self.sqlCursor:
			raise Exception('not connected to database')

		colTypeDict = {}
		if self.sqlType == kDbType_sqlite:
			# Yuck. Sqlite doesn't have a good way to get out the column names and types. Instead we
			# extract out the table CREATE definition, then parse out the column names and types from
			# that statement. Ugly, but works well enough.
			self.sqlCursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?;", (tableName,))
			cleanitem = re.sub(r"[ \t\n\r\f\v]+", ' ', self.sqlCursor.fetchone()[0])
			cleanitem = cleanitem.split(")")[0].split("(")[1].lower()
			colTypeDict = dict([pair.strip().split(" ",1) for pair in cleanitem.split(",")])
		elif self.sqlType == kDbType_postgres:
			self.sqlCursor.execute("SELECT column_name, data_type from information_schema.columns WHERE table_name=%s;", (tableName,))
			for item in self.sqlCursor.fetchall():
				colTypeDict[item[0]] = item[1].lower()
		return colTypeDict


	#/////////////////////////////////////////////////////////////////////////////////////
	# Table modification routines
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will add a new column to the given table
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def AddTableColumn(self, tableName, colName, colType):
		sqlStr = "ALTER TABLE %s ADD COLUMN %s %s;" % (tableName, colName, colType)
		self.ExecuteWithSubstitution(sqlStr);

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will modify the column type of an existing column in a table
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def ModifyTableColumnType(self, tableName, colName, colType):
		if not self.sqlConn or not self.sqlCursor:
			raise Exception('not connected to database')

		if self.sqlType == kDbType_sqlite:
			# The Good News: Because SQLite doesn't care about column types we will probably
			# never need to try to modify a column type. For example, we won't get an error
			# when trying to insert "oak tree" into a BOOL type column. Note SQLite does let
			# you specify a column type in the CREATE table call, but those types are not
			# enforced. So there probably isn't a critical reason to worry about modifying the
			# types after the CREATE if they need to change (besides the fact that it would
			# make the table definition look "more correct").
			#
			# The Bad News: If we do decide to care about this, it is a pain because SQLite
			# doesn't support ALTER COLUMN. The solution is to create a temporary table with
			# the correct types and move over the contents of the previous table. Something
			# roughly like this:
			#
			#		BEGIN TRANSACTION
			#		ALTER TABLE orig_table_name RENAME TO tmp_table_name;
			#		CREATE TABLE orig_table_name (col_a INT, col_b INT, ...);
			#		INSERT INTO orig_table_name(col_a, col_b, ...)
			#		SELECT col_a, colb, ...
			#		FROM tmp_table_name;
			#		DROP TABLE tmp_table_name;
			#		COMMIT;
			#
			raise Exception('modifying SQLite table column types is not supported')
		elif self.sqlType == kDbType_postgres:
			sqlStr = "ALTER TABLE %s ALTER COLUMN %s TYPE %s;" % (tableName, colName, colType)
			self.ExecuteWithSubstitution(sqlStr)


	#/////////////////////////////////////////////////////////////////////////////////////
	# Data retrieval and modification routines
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will prune all of the data in a table that was stamped prior to a date
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def PruneOldTableRows(self, tableName, beforeDateTime):
		if self.IsTypePostgres():
			sqlStr = "DELETE FROM " + tableName + " WHERE ts < %s;"
		elif self.IsTypeSqlite():
			sqlStr = "DELETE FROM " + tableName + " WHERE datetime(ts,'localtime') < %s;"
		if isinstance(beforeDateTime, datetime.datetime):
			self.ExecuteWithSubstitution(sqlStr, (beforeDateTime.isoformat(" "),))
		else:	# assume it is just a date (not datetime), so no arg to isoformat()
			self.ExecuteWithSubstitution(sqlStr, (beforeDateTime.isoformat(),))
			
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will execute a SQL statement as-is
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def ExecuteSQL(self, command, subArgs=None):
		if not self.sqlConnGood:
			raise Exception('not connected to database')

		if self.sqlType == kDbType_sqlite and not subArgs:
			# sqLite doesn't like None specified for args; use empty tuple instead
			subArgs = ()
		
		self.sqlCursor.execute(command, subArgs)
	
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will execute a SQL statement while doing substitution of parameters
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def ExecuteWithSubstitution(self, command, subArgs=None):
		if not self.sqlConnGood:
			raise Exception('not connected to database')

		if self.sqlType == kDbType_sqlite:
			# sqLite uses the ? character for argument substiution
			command = command.replace("%d", "?")
			command = command.replace("%f", "?")
			command = command.replace("%s", "?")
			if not subArgs:		# sqLite doesn't like None specified for args; use empty tuple instead
				subArgs = ()
		elif self.sqlType == kDbType_postgres:
			# postgres uses printf style character for argument substiution
			pass

		command = command.replace("#AUTO_INCR_KEY", self.sqlAutoIncrKey)

		self._DebugLog(command)
		if subArgs:
			self._DebugLog("     %s" % str(subArgs))

		self.sqlCursor.execute(command, subArgs)
		if self.sqlType == kDbType_sqlite:
			self.sqlConn.commit()

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will execute a SQL statement to select the given columns from a table
	# for records that fall within a given date/time range
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def QueryFromTableUsingRange(self, tableName, elemColumn, elemName, startTime, endTime, columnList):
		if self.IsTypePostgres():
			sqlStr = """
				SELECT id, ts, #ELEMCOLUMN, #COLUMNLIST
				FROM #TABLENAME
				WHERE #ELEMCOLUMN = %s AND ts BETWEEN %s AND %s
				ORDER BY id;
			"""
		elif self.IsTypeSqlite():
			sqlStr = """
				SELECT id, ts as 'ts [timestamp]', #ELEMCOLUMN, #COLUMNLIST
				FROM #TABLENAME
				WHERE #ELEMCOLUMN = %s AND datetime(ts,'localtime') BETWEEN %s AND %s
				ORDER BY id;
			"""
		sqlStr = sqlStr.replace("#TABLENAME", tableName)
		sqlStr = sqlStr.replace("#ELEMCOLUMN", elemColumn)
		sqlStr = sqlStr.replace("#COLUMNLIST", ','.join(columnList))

		self.ExecuteWithSubstitution(sqlStr, (elemName, startTime.isoformat(' '), endTime.isoformat(' ')))

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will fetch a single record from the current cursor
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def FetchOne(self):
		if not self.sqlConnGood:
			raise Exception('not connected to database')
		return self.sqlCursor.fetchone()

	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine will fetch all of the records from the current cursor
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def FetchAll(self):
		if not self.sqlConnGood:
			raise Exception('not connected to database')
		return self.sqlCursor.fetchall()
		
		
	#/////////////////////////////////////////////////////////////////////////////////////
	# Utility Routines
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine can format a timestamp column to retrieve the value in the locals
	# time (as opposed to UNC); by default we do no changes
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getLocalTimestampColumn(self, tsColumnName):
		return tsColumnName


#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# IndigoSqlite
#	This concrete implementation allows access to the SQLLite database
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
class IndigoSqlite(IndigoSql):
	
	#/////////////////////////////////////////////////////////////////////////////////////
	# Constructors and Destructors
	#/////////////////////////////////////////////////////////////////////////////////////
	def __init__(self, sql_lite_db_file, sleepFunc, logFunc, debugLogFunc):
		IndigoSql.__init__(self, kDbType_sqlite, sleepFunc, logFunc, debugLogFunc)

		# Create connection to database. Create database and tables if they do not exist.
		try:
			self.sqlmod = __import__('sqlite3', globals(), locals())
			self.sqlmod.register_adapter(bool, adapt_boolean)
			self.sqlmod.register_converter("boolean", convert_boolean)
		except Exception, e:
			self._Log("exception trying to load python sqlite3 module: " + str(e), isError=True)
			raise

		try:
			self.sqlConn = self.sqlmod.connect(sql_lite_db_file, detect_types=self.sqlmod.PARSE_COLNAMES)
			self.sqlCursor = self.sqlConn.cursor()
			self.sqlConnGood = True
			self._Log("connected to " + sql_lite_db_file)
		except Exception, e:
			if self.sqlCursor:
				self.sqlCursor.close()
				self.sqlCursor = None
			if self.sqlConn:
				self.sqlConn.close()
				self.sqlConn = None
			self._Log("exception trying to connect or create database file: %s" % (sql_lite_db_file), isError=True)
			self._Log(str(e), isError=True)
			raise

	
	#/////////////////////////////////////////////////////////////////////////////////////
	# Utility Routines
	#/////////////////////////////////////////////////////////////////////////////////////
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	# This routine can format a timestamp column to retrieve the value in the local
	# time (as opposed to UNC)
	#-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-
	def getLocalTimestampColumn(self, tsColumnName):
		return "datetime(" + tsColumnName + ", 'localtime') as " + tsColumnName


#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
# IndigoPostgresql
#	This concrete implementation allows access to the PostGRE database
#/////////////////////////////////////////////////////////////////////////////////////////
#/////////////////////////////////////////////////////////////////////////////////////////
class IndigoPostgresql(IndigoSql):

	#/////////////////////////////////////////////////////////////////////////////////////
	# Constructors and Destructors
	#/////////////////////////////////////////////////////////////////////////////////////
	def __init__(self, sql_host, sql_user, sql_password, sql_database, sleepFunc, logFunc, debugLogFunc):
		IndigoSql.__init__(self, kDbType_postgres, sleepFunc, logFunc, debugLogFunc)

		# Create connection to database. Create database and tables if they do not exist.
		try:
			self.sqlmod = __import__('', globals(), locals(), ['bpgsql'])
			self.sqlmod = getattr(self.sqlmod, 'bpgsql')
			#self.sqlmod = __import__('MySQLdb', globals(), locals())
		except Exception, e:
			self._Log("exception trying to load python bpgsql module: " + str(e), isError=True)
			raise

		loggedException = False
		try:
			try:
				self.sqlConn = self.sqlmod.connect(host=sql_host, dbname=sql_database, username=sql_user, password=sql_password, timeout=kDbConnectTimeout)
				# additional interesting args: use_unicode=1, charset='utf8'
				self.sqlCursor = self.sqlConn.cursor()
			except socket.error, e:
				# Server likely hasn't started (we could test to see if value == ECONNREFUSED here),
				# so we sleep for a bit and try again. Unfortuantely, IndigoServer can be launched
				# during the OS startup before PostgreSQL has started.
				self._Log("PostgreSQL server %s is not reachable (may not have started yet)" % (sql_host), isError=True)
				loggedException = True
				raise
			except self.sqlmod.DatabaseError, e:
				# Database probably didn't exist, try to create it.
				self.sqlConn = self.sqlmod.connect(host=sql_host, username=sql_user, password=sql_password, timeout=kDbConnectTimeout)
				self.sqlCursor = self.sqlConn.cursor()

				self._Log("creating new database: " + sql_database)
				self.sqlCursor.execute("CREATE DATABASE " + sql_database + ";")

				# No good way to select the new database without recreating the connection.
				self.CloseSqlConnection()
				self.sqlConn = self.sqlmod.connect(host=sql_host, dbname=sql_database, username=sql_user, password=sql_password, timeout=kDbConnectTimeout)
				self.sqlCursor = self.sqlConn.cursor()

			self.sqlConnGood = True
			self._Log("connected to %s as %s on %s" % (sql_database, sql_user, sql_host))
		except Exception, e:
			if self.sqlCursor:
				self.sqlCursor.close()
				self.sqlCursor = None
			if self.sqlConn:
				self.sqlConn.close()
				self.sqlConn = None
			if not loggedException:
				self._Log("exception trying to connect or create database %s on %s" % (sql_database, sql_host), isError=True)
				self._Log(str(e), isError=True)
			raise
