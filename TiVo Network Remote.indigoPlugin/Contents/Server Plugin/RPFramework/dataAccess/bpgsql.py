"""
Barebones PostgreSQL

Copyright 2001-2004 by Barry Pederson <bp@barryp.org>
All rights reserved.

Permission to use, copy, modify, and distribute this software and its
documentation for any purpose and without fee is hereby granted,
provided that the above copyright notice appear in all copies and that
both that copyright notice and this permission notice appear in
supporting documentation, and that the copyright owner's name not be
used in advertising or publicity pertaining to distribution of the
software without specific, written prior permission.

THE AUTHOR(S) DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE,
INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS.  IN
NO EVENT SHALL THE AUTHOR(S) BE LIABLE FOR ANY SPECIAL, INDIRECT OR
CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE
OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE
USE OR PERFORMANCE OF THIS SOFTWARE.

    2001-10-28  Started
    2002-04-06  Changed connect args to be more like the Python DB-API
    2004-03-27  Reworked to follow DB-API 2.0 (http://www.python.org/peps/pep-0249.html)
    2008-03-24  Added support for unicode arguments. (Perceptive Automation change)

"""
import errno, select, socket, sys, types
from struct import pack as _pack
from struct import unpack as _unpack

#
# Module Globals specified by DB-API 2.0
#
apilevel = '2.0'
threadsafety = 1          # Threads may share the module, but not connections.
paramstyle = 'pyformat'   # we also understand plain-format

#
# Exception hierarchy from DB-API 2.0 spec
#
import exceptions
class Error(exceptions.StandardError):
    pass

class Warning(exceptions.StandardError):
    pass

class InterfaceError(Error):
    pass

class DatabaseError(Error):
    pass

class InternalError(DatabaseError):
    pass

class OperationalError(DatabaseError):
    pass

class ProgrammingError(DatabaseError):
    pass

class IntegrityError(DatabaseError):
    pass

class DataError(DatabaseError):
    pass

class NotSupportedError(DatabaseError):
    pass


#
# Custom exceptions raised by this driver
#

class PostgreSQL_Timeout(InterfaceError):
    pass


def _bool_convert(s):
    """
    Convert PgSQL boolean string to Python boolean

    """
    if s == 't':
        return True
    if s == 'f':
        return False
    raise InterfaceError('Boolean type came across as unknown value [%s]' % s)


#
# Map of Pgsql type-names to Python conversion-functions.
#
# The value associated with each key must be a callable Python
# object that takes a string as a parameter, and returns another
# Python object.
#
# PostgreSQL types not listed here stay represented as plain
# strings in result rows.
#
PGSQL_TO_PYTHON_TYPES = {   
                            'bool': _bool_convert,
                            'float4': float,
                            'float8': float,
                            'int2': int,
                            'int4': int,
                            'int8': long,
                            'oid' : long,
                            'numeric': float        #Should be some kind of decimal?
                            }

#
# Constants relating to Large Object support
#
INV_WRITE   = 0x00020000
INV_READ    = 0x00040000

SEEK_SET    = 0
SEEK_CUR    = 1
SEEK_END    = 2

DEBUG = 0



def _parseDSN(s):
    """
    Parse a string containing PostgreSQL libpq-style connection info in the form:

       "keyword1=val1 keyword2='val2 with space' keyword3 = val3"

    into a dictionary::

       {'keyword1': 'val1', 'keyword2': 'val2 with space', 'keyword3': 'val3'}

    Returns empty dict if s is empty string or None.
    """
    if not s:
        return {}

    result = {}
    state = 1
    buf = ''
    for ch in s.strip():
        if state == 1:        # reading keyword
            if ch in '=':
                keyword = buf.strip()
                buf = ''
                state = 2
            else:
                buf += ch
        elif state == 2:        # have read '='
            if ch == "'":
                state = 3
            elif ch != ' ':
                buf = ch
                state = 4
        elif state == 3:        # reading single-quoted val
            if ch == "'":
                result[keyword] = buf
                buf = ''
                state = 1
            else:
                buf += ch
        elif state == 4:        # reading non-quoted val
            if ch == ' ':
                result[keyword] = buf
                buf = ''
                state = 1
            else:
                buf += ch
    if state == 4:              # was reading non-quoted val when string ran out
        result[keyword] = buf
    return result


def _fix_arg(a):
    #
    # Make an argument SQL-ready: replace None with 'NULL', and escape strings
    #
    if a is None:
        return 'NULL'

    # Perceptive Automation (matt) change:
    # Was:
    #    if type(a) == types.StringType:
    # Changed to isinstance to support Unicode:
    if isinstance(a, basestring):
#       return "'%s'" % a.replace('\\', '\\\\').replace("'", "''")	# broken
        return "'%s'" % a.replace('\\', '\\\\').replace("'", "''")	# works
# Perceptive Automation (matt) change:
# Newer versions of PostgreSQL require '' to escape single quotes
# versus the older \' technique.

    return a


class _LargeObject:
    """
    Make a PostgreSQL Large Object look somewhat like
    a Python file.  Should be created from Connection object
    open or create methods.
    """
    def __init__(self, client, fd):
        self.__client = client
        self.__fd = fd

    def __del__(self):
        if self.__client:
            self.close()

    def close(self):
        """
        Close an opened Large Object
        """
        try:
            self.__client._lo_funcall('lo_close', self.__fd)
        finally:
            self.__client = self.__fd = None

    def flush(self):
        pass

    def read(self, len):
        return self.__client._lo_funcall('loread', self.__fd, len)

    def seek(self, offset, whence):
        self.__client._lo_funcall('lo_lseek', self.__fd, offset, whence)

    def tell(self):
        r = self.__client._lo_funcall('lo_tell', self.__fd)
        return _unpack('!i', r)[0]

    def write(self, data):
        """
        Write data to lobj, return number of bytes written
        """
        r = self.__client._lo_funcall('lowrite', self.__fd, data)
        return _unpack('!i', r)[0]


class _ResultSet:
    #
    # Helper class only used internally by the Connection class
    #
    def __init__(self):
        self.conversion = None
        self.description = None
        self.error = None
        self.null_byte_count = 0
        self.num_fields = 0
        self.rows = None
        self.messages = []


    def set_description(self, desc_list):
        self.description = desc_list
        self.num_fields = len(desc_list)
        self.null_byte_count = (self.num_fields + 7) >> 3
        self.rows = []


def _identity(d):
    """
    Identity function, returns whatever was passed to it,
    used when we have a PostgreSQL type for which we don't
    have a function to convert from a PostgreSQL string
    representation to a Python object - so the item
    basically remains a string.
    """
    return d


class Connection:
    """
    connection objects are created by calling this module's connect function.

    """
    def __init__(self, dsn=None, username='', password='', host=None, dbname='', port='', timeout=60, opt=''):
        self.__backend_pid = None
        self.__backend_key = None
        self.__socket = None
        self.__input_buffer = ''
        self.__authenticated = 0
        self.__ready = 0
        self.__result = None
        self.__current_result = None
        self.__notify_queue = []
        self.__func_result = None
        self.__lo_funcs = {}
        self.__lo_funcnames = {}
        self.__type_oid_name = {}         # map of Pgsql type-oids to Pgsql type-names
        self.__type_oid_conversion = {}   # map of Pgsql type-oids to Python conversion_functions

        #
        # Come up with a reasonable default host for
        # win32 and presumably Unix platforms
        #
        if host == None:
            if sys.platform == 'win32':
                host = '127.0.0.1'
            else:
                host = '/tmp/.s.PGSQL.5432'

        args = _parseDSN(dsn)

        if not args.has_key('host'):
            args['host'] = str(host)
        if not args.has_key('port'):
            args['port'] = port or 5432
        if not args.has_key('dbname'):
            args['dbname'] = str(dbname)
        if not args.has_key('user'):
            args['user'] = str(username)
        if not args.has_key('password'):
            args['password'] = str(password)
        if not args.has_key('options'):
            args['options'] = str(opt)
		
        if args['host'].startswith('/'):
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect(args['host'])
        else:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((args['host'], int(args['port'])))

        if not args['user']:
            #
            # If no userid specified in the args, try to use the userid
            # this process is running under, if we can figure that out.
            #
            try:
                import os, pwd
                args['user'] = pwd.getpwuid(os.getuid())[0]
            except:
                pass

        self.__socket = s
        self.__passwd = args['password']
        self.__userid = args['user']

        #
        # Send startup packet specifying protocol version 2.0
        #  (works with PostgreSQL 6.3 or higher?)
        #
        self.__send(_pack('!ihh64s32s64s64s64s', 296, 2, 0, args['dbname'], args['user'], args['options'], '', ''))
        while not self.__ready:
            self.__read_response()

        #
        # Get type info from the backend to help put together some dictionaries
        # to help in converting Pgsql types to Python types.
        #
        self.__initialize_type_map()


    def __del__(self):
        if self.__socket:
            self.__send('X')
            self.__socket.close()
            self.__socket = None


    def __initialize_type_map(self):
        """
        Query the backend to find out a mapping for type_oid -> type_name, and
        then lookup the map of type_name -> conversion_function, to come up
        with a map of type_oid -> conversion_function
        """
        cur = self.cursor()
        cur.execute('SELECT oid, typname FROM pg_type')

        # Make a dictionary of type oids to type names
        self.__type_oid_name = dict([(int(x[0]), x[1]) for x in cur])

        # Fill a dictionary of type oids to conversion functions
        for oid, typename in self.__type_oid_name.items():
            self.__type_oid_conversion[oid] = PGSQL_TO_PYTHON_TYPES.get(typename, _identity)


    def __lo_init(self):
        #
        # Make up a dictionary mapping function names beginning with "lo" to function oids
        # (there may be some non-lobject functions in there, but that should be harmless)
        #
        descr, rows, msgs = self._execute("SELECT proname, oid FROM pg_proc WHERE proname like 'lo%'")
        for proname, oid in rows:
            self.__lo_funcs[proname] = oid
            self.__lo_funcnames[oid] = proname


    def __new_result(self):
        #
        # Start a new ResultSet
        #
        if self.__result is None:
            self.__result = []
        self.__current_result = _ResultSet()
        self.__result.append(self.__current_result)


    def __read_bytes(self, nBytes):
        #
        # Read the specified number of bytes from the backend
        #
        if DEBUG:
            print '__read_bytes(%d)' % nBytes

        while len(self.__input_buffer) < nBytes:
            d = self.__recv(4096)
            if d:
                self.__input_buffer += d
            else:
                raise OperationalError('Connection to backend closed')
        result, self.__input_buffer = self.__input_buffer[:nBytes], self.__input_buffer[nBytes:]
        return result


    def __read_string(self, terminator='\0'):
        #
        # Read a something-terminated string from the backend
        # (the terminator isn't returned as part of the result)
        #
        result = None
        while 1:
            try:
                result, self.__input_buffer = self.__input_buffer.split(terminator, 1)
                return result
            except:
                # need more data
                d = self.__recv(4096)
                if d:
                    self.__input_buffer += d
                else:
                    raise OperationalError('Connection to backend closed')


    def __read_response(self):
        #
        # Read a single response from the backend
        #  Looks at the next byte, and calls a more specific
        #  method the handle the rest of the response
        #
        #  PostgreSQL responses begin with a single character <c>, this
        #  method looks up a method named _pkt_<c> and calls that
        #  to handle the response
        #
        if DEBUG:
            print '>[%s]' % self.__input_buffer

        pkt_type = self.__read_bytes(1)

        if DEBUG:
            print 'pkt_type:', pkt_type

        method = self.__class__.__dict__.get('_pkt_' + pkt_type, None)
        if method:
            method(self)
        else:
            raise InterfaceError('Unrecognized packet type from server: %s' % pkt_type)


    def __read_row(self, ascii=1):
        #
        # Read an ASCII or Binary Row
        #
        result = self.__current_result

        # check if we need to use longs (more than 32 fields)
        if result.null_byte_count > 4:
            null_bits = 0L
            field_mask = 128L
        else:
            null_bits = 0
            field_mask = 128

        # read bytes holding null bits and setup the field mask
        # to point at the first (leftmost) field
        if result.null_byte_count:
            for ch in self.__read_bytes(result.null_byte_count):
                null_bits = (null_bits << 8) | ord(ch)
            field_mask <<= (result.null_byte_count - 1) * 8

        # read each field into a row
        row = []
        for field_num in range(result.num_fields):
            if null_bits & field_mask:
                # field has data present, read what was sent
                field_size = _unpack('!i', self.__read_bytes(4))[0]
                if ascii:
                    field_size -= 4
                data = self.__read_bytes(field_size)
                row.append(result.conversion[field_num](data))
            else:
                # field has no data (is null)
                row.append(None)
            field_mask >>= 1

        result.rows.append(row)


    def __recv(self, bufsize):
        while 1:
            try:
                return self.__socket.recv(bufsize)
            except socket.error, serr:
                if serr[0] != errno.EINTR:
                    raise


    def __send(self, data):
        #
        # Send data to the backend, make sure it's all sent
        #
        if DEBUG:
            print 'Send [%s]' % data

        if self.__socket is None:
            raise InterfaceError, 'Connection not open'

        while data:
            try:
                nSent = self.__socket.send(data)
            except socket.error, serr:
                if serr[0] != errno.EINTR:
                    raise
                continue
            data = data[nSent:]


    def __wait_response(self, timeout):
        #
        # Wait for something to be in the input buffer, timeout
        # is a floating-point number of seconds, zero means
        # timeout immediately, < 0 means don't timeout (call blocks
        # indefinitely)
        #
        if self.__input_buffer:
            return 1

        if timeout >= 0:
            r, w, e = select.select([self.__socket], [], [], timeout)
        else:
            r, w, e = select.select([self.__socket], [], [])

        if r:
            return 1
        else:
            return 0



    #-----------------------------------
    #  Packet Handling Methods
    #

    def _pkt_A(self):
        #
        # Notification Response
        #
        pid = _unpack('!i', self.__read_bytes(4))[0]
        self.__notify_queue.append((self.__read_string(), pid))


    def _pkt_B(self):
        #
        # Binary Row
        #
        print self.__read_row(0)


    def _pkt_C(self):
        #
        # Completed Response
        #
        self.__current_result.completed = self.__read_string()
        self.__new_result()


    def _pkt_D(self):
        #
        # ASCII Row
        #
        self.__read_row()


    def _pkt_E(self):
        #
        # Error Response
        #
        if self.__current_result:
            self.__current_result.error = self.__read_string()
            self.__new_result()
        else:
            raise DatabaseError(self.__read_string())


    def _pkt_G(self):
        #
        # CopyIn Response from self.stdin if available, or
        # sys.stdin   Supplies the final terminating line:
        #  '\.' (one backslash followd by a period) if it
        # doesn't appear in the input
        #
        if hasattr(self, 'stdin') and self.stdin:
            stdin = self.stdin
        else:
            stdin = sys.stdin

        lastline = None
        while 1:
            s = stdin.readline()
            if (not s) or (s == '\\.\n'):
                break
            self.__send(s)
            lastline = s
        if lastline and (lastline[-1] != '\n'):
            self.__send('\n')
        self.__send('\\.\n')


    def _pkt_H(self):
        #
        # CopyOut Response to self.stdout if available, or
        # sys.stdout    Doesn't write the final terminating line:
        #  '\.'  (one backslash followed by a period)
        #
        if hasattr(self, 'stdout') and self.stdout:
            stdout = self.stdout
        else:
            stdout = sys.stdout

        while 1:
            s = self.__read_string('\n')
            if s == '\\.':
                break
            else:
                stdout.write(s)
                stdout.write('\n')


    def _pkt_I(self):
        #
        # EmptyQuery Response
        #
        if DEBUG:
            print 'Empty Query', self.__read_string()


    def _pkt_K(self):
        #
        # Backend Key data
        #
        self.__backend_pid, self.__backend_key = _unpack('!ii', self.__read_bytes(8))
        #print 'Backend Key Data, pid: %d, key: %d' % (self.__backend_pid, self.__backend_key)


    def _pkt_N(self):
        #
        # Notice Response
        #
        n = self.__read_string()
        if DEBUG:
            print 'Notice:', n
        self.__current_result.messages.append((Warning, n))


    def _pkt_P(self):
        #
        # Cursor Response
        #
        cursor = self.__read_string()


    def _pkt_R(self):
        #
        # Startup Response
        #
        code = _unpack('!i', self.__read_bytes(4))[0]
        if code == 0:
            self.__authenticated = 1
            #print 'Authenticated!'
        elif code == 1:
            raise InterfaceError('Kerberos V4 authentication is required by server, but not supported by this client')
        elif code == 2:
            raise InterfaceError('Kerberos V5 authentication is required by server, but not supported by this client')
        elif code == 3:
            self.__send(_pack('!i', len(self.__passwd)+5) + self.__passwd + '\0')
        elif code == 4:
            salt = self.__read_bytes(2)
            try:
                import crypt
            except:
                raise InterfaceError('Encrypted authentication is required by server, but Python crypt module not available')
            cpwd = crypt.crypt(self.__passwd, salt)
            self.__send(_pack('!i', len(cpwd)+5) + cpwd + '\0')
        elif code == 5:
            import md5

            m = md5.new(self.__passwd + self.__userid).hexdigest()
            m = md5.new(m + self.__read_bytes(4)).hexdigest()
            m = 'md5' + m + '\0'
            self.__send(_pack('!i', len(m)+4) + m)
        else:
            raise InterfaceError('Unknown startup response code: R%d (unknown password encryption?)' % code)


    def _pkt_T(self):
        #
        # Row Description
        #
        nFields = _unpack('!h', self.__read_bytes(2))[0]
        descr = []
        for i in range(nFields):
            fieldname = self.__read_string()
            oid, type_size, type_modifier = _unpack('!ihi', self.__read_bytes(10))
            descr.append((fieldname, oid, type_size, type_modifier))

        # Save the field description list
        self.__current_result.set_description(descr)

        # build a list of field conversion functions we can use against each row
        self.__current_result.conversion = [self.__type_oid_conversion.get(d[1], _identity) for d in descr]


    def _pkt_V(self):
        #
        # Function call response
        #
        self.__func_result = None
        while 1:
            ch = self.__read_bytes(1)
            if ch == '0':
                break
            if ch == 'G':
                result_size = _unpack('!i', self.__read_bytes(4))[0]
                self.__func_result = self.__read_bytes(result_size)
            else:
                raise InterfaceError('Unexpected byte: [%s] in Function call reponse' % ch)


    def _pkt_Z(self):
        #
        # Ready for Query
        #
        self.__ready = 1
        #print 'Ready for Query'


    #--------------------------------------
    # Helper func for _LargeObject
    #
    def _lo_funcall(self, name, *args):
        return apply(self.funcall, (self.__lo_funcs[name],) + args)


    #--------------------------------------
    # Helper function for Cursor objects
    #
    def _execute(self, cmd, args=None):
        if args is not None:
            argtype = type(args)
            if argtype not in [types.TupleType, types.DictType]:
                args = (args,)
                argtype = types.TupleType

            # At this point we know args is either a tuple or a dict

            if argtype == types.TupleType:
                # Replace plain-format markers with fixed-up tuple parameters
                cmd = cmd % tuple([_fix_arg(a) for a in args])
            else:
                # replace pyformat markers with dictionary parameters
                cmd = cmd % dict([(k, _fix_arg(v)) for k,v in args.items()])

        # Perceptive Automation (matt) change:
        # Must encode unicode strings into UTF8 first.
        if type(cmd)==type(u''):
            cmd = cmd.encode("utf-8")

        self.__ready = 0
        self.__result = None
        self.__new_result()
        self.__send('Q'+cmd+'\0')
        while not self.__ready:
            self.__read_response()
        result, self.__result = self.__result[:-1], None

        # Convert old-style results to what the new Cursor class expects
        result = result[0]

        if result.error:
            raise DatabaseError, result.error

        # Convert Pgsql row descriptions to DB-API 2.0 row descriptions, somewhat... ###FIXME###
        descr = result.description
        if descr:
            descr = [(x[0], self.__type_oid_name.get(x[1], '???'), None, None, None, None, None) for x in descr]

        return descr, result.rows, result.messages



    #--------------------------------------
    # Public methods
    #

    def close(self):
        """
        Close the connection now (rather than whenever __del__ is
        called).  The connection will be unusable from this point
        forward; an Error (or subclass) exception will be raised
        if any operation is attempted with the connection. The
        same applies to all cursor objects trying to use the
        connection.

        """
        if self.__socket is None:
            raise InterfaceError, "Can't close connection that's not open"
        self.__del__()


    def commit(self):
        """
        Commit any pending transaction to the database.

        """
        self._execute('COMMIT')


    def cursor(self):
        """
        Get a new cursor object using this connection.

        """
        return Cursor(self)


    def funcall(self, oid, *args):
        """
        Low-level call to PostgreSQL function, you must supply
        the oid of the function, and have the args supplied as
        ints or strings.

        """
        if DEBUG:
            funcname = self.__lo_funcnames.get(oid, str(oid))
            print 'funcall', funcname, args

        self.__ready = 0
        self.__send(_pack('!2sIi', 'F\0', oid, len(args)))
        for arg in args:
            atype = type(arg)
            if (atype == types.LongType) and (arg >= 0):
                # Make sure positive longs, such as OIDs, get sent back as unsigned ints
                self.__send(_pack('!iI', 4, arg))
            elif (atype == types.IntType) or (atype == types.LongType):
                self.__send(_pack('!ii', 4, arg))
            else:
                self.__send(_pack('!i', len(arg)))
                self.__send(arg)

        while not self.__ready:
            self.__read_response()
        result, self.__func_result = self.__func_result, None
        return result


    def lo_create(self, mode=INV_READ|INV_WRITE):
        """
        Return the oid of a new Large Object, created with the specified mode

        """
        if not self.__lo_funcs:
            self.__lo_init()
        r = self.funcall(self.__lo_funcs['lo_creat'], mode)
        return _unpack('!i', r)[0]


    def lo_open(self, oid, mode=INV_READ|INV_WRITE):
        """
        Open the Large Object with the specified oid, returns
        a file-like object

        """
        if not self.__lo_funcs:
            self.__lo_init()
        r = self.funcall(self.__lo_funcs['lo_open'], oid, mode)
        fd = _unpack('!i', r)[0]
        lobj =  _LargeObject(self, fd)
        lobj.seek(0, SEEK_SET)
        return lobj


    def lo_unlink(self, oid):
        """
        Delete the specified Large Object

        """
        if not self.__lo_funcs:
            self.__lo_init()
        self.funcall(self.__lo_funcs['lo_unlink'], oid)


    def rollback(self):
        """
        Cause the the database to roll back to the start of any
        pending transaction.

        """
        self._execute('ROLLBACK')


    def wait_for_notify(self, timeout=-1):
        """
        Wait for an async notification from the backend, which comes
        when another client executes the SQL command:

           NOTIFY name

        where 'name' is an arbitrary string. timeout is specified in
        floating- point seconds, -1 means no timeout, 0 means timeout
        immediately if nothing is available.

        In practice though the timeout is a timeout to wait for the
        beginning of a message from the backend. Once a message has
        begun, the client will wait for the entire message to finish no
        matter how long it takes.

        Return value is a tuple: (name, pid) where 'name' string
        specified in the NOTIFY command, and 'pid' is the pid of the
        backend process that processed the command.

        Raises a PostgreSQL_Timeout exception on timeout

        """
        while 1:
            if self.__notify_queue:
                result, self.__notify_queue = self.__notify_queue[0], self.__notify_queue[1:]
                return result
            if self.__wait_response(timeout):
                self.__read_response()
            else:
                raise PostgreSQL_Timeout()


class Cursor:
    """
    Cursor objects are created by calling a connection's cursor() method,
    and are used to manage the context of a fetch operation.

    Cursors created from the same connection are not isolated, i.e., any changes
    done to the database by a cursor are immediately visible by the
    other cursors.

    Cursors created from different connections are isolated.

    """
    def __init__(self, conn):
        """
        Create a cursor from a given bpgsql Connection object.

        """
        self.arraysize = 1
        self.connection = conn
        self.description = None
        self.lastrowid = None
        self.messages = []
        self.rowcount = -1
        self.rownumber = None
        self.__rows = None


    def __iter__(self):
        """
        Return an iterator for the result set this cursor holds.

        """
        return self


    def close(self):
        """
        Close the cursor now (rather than whenever __del__ is
        called).  The cursor will be unusable from this point
        forward; an Error (or subclass) exception will be raised
        if any operation is attempted with the cursor.

        """
        self.__init__(None)


    def execute(self, cmd, args=None):
        """
        Execute a database operation (query or command).
        Parameters may be provided as sequence or
        mapping or singleton argument and will be bound to variables
        in the operation. Variables are specified in format (...WHERE foo=%s...)
        or pyformat (...WHERE foo=%(name)s...) paramstyles.

        """
        self.rowcount = -1
        self.rownumber = None
        self.description = None
        self.__rows = None
        self.messages = []

        self.description, self.__rows, self.messages = self.connection._execute(cmd, args)

        if self.__rows is not None:
            self.rowcount = len(self.__rows)
            self.rownumber = 0


    def executemany(self, str,  seq_of_parameters):
        """
        Execute a database operation (query or command) against
        all parameter sequences or mappings found in the
        sequence seq_of_parameters.

        """
        for p in seq_of_parameters:
            self.execute(str, p)


    def fetchall(self):
        """
        Fetch all remaining rows of a query set, as a list of lists.
        An empty list is returned if no more rows are available.
        An Error is raised if no result set exists

        """
        if self.__rows is None:
            raise Error, 'No result set available'

        return self.fetchmany(self.rowcount - self.rownumber)


    def fetchone(self):
        """
        Fetch the next row of the result set as a list of fields, or None if
        no more are available.  Will raise an Error if no
        result set exists.

        """
        try:
            return self.next()
        except StopIteration:
            return None


    def fetchmany(self, size=None):
        """
        Fetch all the specified number of rows of a query set, as a list of lists.
        If no size is specified, then the cursor's .arraysize property is used.
        An empty list is returned if no more rows are available.
        An Error is raised if no result set exists

        """
        if self.__rows is None:
            raise Error, 'No result set available'

        if size is None:
            size = self.arraysize

        n = self.rownumber
        self.rownumber += size
        return self.__rows[n:self.rownumber]


    def next(self):
        """
        Return the next row of a result set.  Raises StopIteration
        if no more rows are available.  Raises an Error if no result set
        exists.

        """
        if self.__rows is None:
            raise Error, 'No result set available'

        n = self.rownumber
        if n >= self.rowcount:
            raise StopIteration

        self.rownumber += 1
        return self.__rows[n]


    def scroll(self, n, mode='relative'):
        """
        Scroll the cursor in the result set to a new position according
        to mode.

        If mode is 'relative' (default), value is taken as offset to
        the current position in the result set, if set to 'absolute',
        value states an absolute target position.

        An IndexError will be raised in case a scroll operation would
        leave the result set. In this case, the cursor position unchanged.

        """
        if self.__rows is None:
            raise Error, 'No result set available'

        if mode == 'relative':
            newpos = self.rownumber + n
        elif mode == 'absolute':
            newpos = n
        else:
            raise ProgrammingError, 'Unknown scroll mode [%s]' % mode

        if (newpos < 0) or (newpos >= self.rowcount):
            raise IndexError, 'scroll(%d, "%s") target position: %d outsize of range: 0..%d' % (n, mode, newpos, self.rowcount-1)

        self.rownumber = newpos


    def setinputsizes(self, sizes):
        """
        Intented to be used before a call to executeXXX() to
        predefine memory areas for the operation's parameters.

        Doesn't actually do anything in this client.

        """
        pass


    def setoutputsize(self, size, column=None):
        """
        Set a column buffer size for fetches of large columns
        (e.g. LONGs, BLOBs, etc.).

        Doesn't actually do anything in this client.

        """
        pass


def connect(dsn=None, username='', password='', host=None, dbname='', port='', timeout=60, opt='', **extra):
    """
    Connect to a PostgreSQL database.

    The dsn, if used, is in the format used by the PostgreSQL libpq C library, which is one
    or more "keyword=value" pairs separated by spaces.  Values that are single-quoted may
    contain spaces.  Spaces around the '=' chars are ignored.  Recognized keywords are:

          host, port, dbname, user, password, options

    For example:

          cnx = bpgsql.connect("host=127.0.0.1 dbname=mydb user=jake")

    """
    return Connection(dsn, username, password, host, dbname, port, timeout, opt)

# ---- EOF ----
