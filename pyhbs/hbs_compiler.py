from functools import partial
import re

from .grammar import OMeta

import collections

import datetime
import time
import json
import math
import os

handlebars_grammar = r"""
template ::= (<text> | <templatecommand>)*:body => ['template'] + body
text ::= (~(<start>) <anything>)+:text => ('literal', ''.join(text))
other ::= <anything>:char => ('literal', char)
templatecommand ::= <blockrule>
    | <comment>
    | <escapedexpression>
    | <expression>
    | <partial>
start ::= '{' '{'
finish ::= '}' '}'
comment ::= <start> '!' (~(<finish>) <anything>)* <finish> => ('comment', )
space ::= ' '|'\t'|'\r'|'\n'
arguments ::= (<space>+ (<kwliteral>|<literal>|<path>))*:arguments => arguments
expression_inner ::= <spaces> <path>:p <arguments>:arguments <spaces> <finish> => (p, arguments)
expression ::= <start> '{' <expression_inner>:e '}' => ('expand', ) + e
    | <start> '&' <expression_inner>:e => ('expand', ) + e
escapedexpression ::= <start> <expression_inner>:e => ('escapedexpand', ) + e
block_inner ::= <spaces> <symbol>:s <arguments>:args <spaces> <finish>
    => (''.join(s), args)
alt_inner ::= <spaces> ('^' | 'e' 'l' 's' 'e') <spaces> <finish>
partial ::= <start> '>' <block_inner>:i => ('partial',) + i
path ::= ~('/') <pathseg>+:segments => ('path', segments)
kwliteral ::= <symbol>:s '=' (<literal>|<path>):v => ('kwparam', s, v)
literal ::= (<string>|<integer>|<boolean>):thing => ('literalparam', thing)
string ::= '"' <notquote>*:ls '"' => '"' + ''.join(ls) + '"'
integer ::= <digit>+:ds => int(''.join(ds))
boolean ::= <false>|<true>
false ::= 'f' 'a' 'l' 's' 'e' => False
true ::= 't' 'r' 'u' 'e' => True
notquote ::= <escapedquote> | (~('"') <anything>)
escapedquote ::= '\\' '"' => '\\"'
symbol ::=  ~<alt_inner> '['? (<letterOrDigit>|'-'|'@')+:symbol ']'? => ''.join(symbol)
pathseg ::= <symbol>
    | '/' => ''
    | ('.' '.' '/') => '__parent'
    | '.' => ''
pathfinish :expected ::= <start> '/' <path>:found ?(found == expected) <finish>
symbolfinish :expected ::= <start> '/' <symbol>:found ?(found == expected) <finish>
blockrule ::= <start> '#' <block_inner>:i
      <template>:t <alttemplate>:alt_t <symbolfinish i[0]> => ('block',) + i + (t, alt_t)
    | <start> '^' <block_inner>:i
      <template>:t <symbolfinish i[0]> => ('invertedblock',) + i + (t,)
alttemplate ::= (<start> <alt_inner> <template>)?:alt_t => alt_t or []
"""

compile_grammar = """
compile ::= <prolog> <rule>* => builder.finish()
prolog ::= "template" => builder.start()
compile_block ::= <prolog_block> <rule>* => builder.finish_block()
prolog_block ::= "template" => builder.start_block()
rule ::= <literal>
    | <expand>
    | <escapedexpand>
    | <comment>
    | <block>
    | <invertedblock>
    | <partial>
block ::= [ "block" <anything>:symbol [<arg>*:arguments] [<compile_block>:t] [<compile_block>?:alt_t] ] => builder.add_block(symbol, arguments, t, alt_t)
comment ::= [ "comment" ]
literal ::= [ "literal" :value ] => builder.add_literal(value)
expand ::= [ "expand" <path>:value [<arg>*:arguments]] => builder.add_expand(value, arguments)
escapedexpand ::= [ "escapedexpand" <path>:value [<arg>*:arguments]] => builder.add_escaped_expand(value, arguments)
invertedblock ::= [ "invertedblock" <anything>:symbol [<arg>*:arguments] [<compile>:t] ] => builder.add_invertedblock(symbol, arguments, t)
partial ::= ["partial" <anything>:symbol [<arg>*:arguments]] => builder.add_partial(symbol, arguments)
path ::= [ "path" [<pathseg>:segment]] => ("simple", segment)
 | [ "path" [<pathseg>+:segments] ] => ("complex", 'resolve(context, "'  + '","'.join(segments) + '")' )
simplearg ::= [ "path" [<pathseg>+:segments] ] => 'resolve(context, "'  + '","'.join(segments) + '")'
    | [ "literalparam" <anything>:value ] => str(value)
arg ::= [ "kwparam" <anything>:symbol <simplearg>:a ] => str(symbol) + '=' + a
    | <simplearg>
pathseg ::= "/" => ''
    | "." => ''
    | "" => ''
    | "this" => ''
pathseg ::= <anything>:symbol => ''.join(symbol)
"""
compile_grammar = compile_grammar.format()

class strlist(list):

    def __str__(self):
        return ''.join(self)

    def grow(self, thing):
        if type(thing) == str:
            self.append(thing)
        else:
            for element in thing:
                self.grow(element)

_map = {
    '&': '&amp;',
    '"': '&quot;',
    "'": '&#x27;',
    '`': '&#x60;',
    '<': '&lt;',
    '>': '&gt;',
}

def substitute(match, _map=_map):
    return _map[match.group(0)]

_escape_re = re.compile(r"&|\"|'|`|<|>")

def escape(something, _escape_re=_escape_re, substitute=substitute):
    return _escape_re.sub(substitute, something)

class Scope:

    def __init__(self, context, parent, data=None):
        self.context = context
        self.parent = parent
        if parent and isinstance(parent,Scope):
            self.data=parent.data
        else:
            self.data={}
        if data:
            self.data.update(data)

    def get(self, name, default=None):
        if name == '__parent':
            return self.parent
        elif name == 'this':
            return self.context
        elif name.startswith("@"):
            return self.data.get(name[1:])
        result = self.context.get(name, self)
        if result is not self:
            return result
        return default
    __getitem__ = get

    def __str__(self):
        return str(self.context)

def resolve(context, *segments):
    # print("resolve",segments)
    for segment in segments:
        if context is None:
            return None
        if segment in (None, ""):
            continue
        if type(context) in (list, tuple):
            offset = int(segment)
            try:
                context = context[offset]
            except:
                context = None
        else:
            if isinstance(segment, str) and segment.isdigit():
                segment = int(segment)
            context = context.get(segment)
    return context

def _paginate(this, options, data, limit=None, offset=None, url=None):
    if not data:
        return options['inverse'](this)
    if limit is None:
        limit = 10
    if offset is None:
        offset = 0
    count = len(data)
    page_no = math.floor(offset / limit) + 1
    num_pages = math.floor((count + limit - 1) / limit)
    paginate = {
        "data": data[offset:offset + limit],
        "limit": limit,
        "offset": offset,
        "count": count,
        "item_first": offset + 1,
        "item_last": min(offset + limit, count),
        "page_no": page_no,
        "num_pages": num_pages,
        "parts": [],
    }
    if url:
        base_url = re.sub("&offset=\d+", "", url)  # XXX
    else:
        base_url = ""
    if base_url.find("?")==-1: # XXX
        base_url+="?"
    if page_no > 1:
        p = page_no - 1
        o = (p - 1) * limit
        paginate["previous"] = {
            "page_no": p,
            "url": base_url + "&offset=%d" % o if base_url else None,
        }
    if page_no < num_pages:
        p = page_no + 1
        o = (p - 1) * limit
        paginate["next"] = {
            "page_no": p,
            "url": base_url + "&offset=%d" % o if base_url else None,
        }
    if num_pages > 1:
        first_part_page_no = max(1, page_no - 2)
        last_part_page_no = min(num_pages, page_no + 1)
        for p in range(first_part_page_no, last_part_page_no + 1):
            o = (p - 1) * limit
            part = {
                "page_no": p,
                "active": p == page_no,
                "url": base_url + "&offset=%d" % o if base_url else None,
            }
            paginate["parts"].append(part)
    scope = Scope({"paginate": paginate}, this)
    return options['fn'](scope)

def _each(this, options, context, order=None, offset=None, limit=None):
    if not context:
        return None
    result = strlist()
    i = 0
    if order:
        if len(order.split(" ")) == 2:
            if order.split(" ")[1] == "desc":
                context2 = sorted(context, key=lambda x: x[order.split(" ")[0]])[::-1]
        else:
            context2 = sorted(context, key=lambda x: x[order])
    else:
        context2 = context
    if offset:
        context2=context2[offset:]
    if limit:
        context2=context2[:limit]
    for ctx in context2:
        scope = Scope(ctx, this, {})
        result.grow(options['fn'](scope))
        i += 1
    return result

def _if(this, options, context):
    if isinstance(context, collections.Callable):
        context = context(this)
    if context:
        return options['fn'](this)
    else:
        return options['inverse'](this)

def _unless(this, options, context):
    if not context:
        return options['fn'](this)

def _blockHelperMissing(this, options, context):
    if isinstance(context, collections.Callable):
        context = context(this)
    if context != "" and not context:
        return options['inverse'](this)
    if type(context) in (list, strlist, tuple):
        return _each(this, options)
    if context is True:
        callwith = this
    else:
        callwith = context
    return options['fn'](callwith)

def _helperMissing(scope, name, *args):
    if not args:
        return None
    raise Exception("Could not find property %s" % (name,))

def _with(this, options, context):
    if context:
        scope = Scope(context, this)
        return options['fn'](scope)
    else:
        return options['inverse'](this)

def _compare(this, options, val1, val2, operator="="):
    if operator == "=":
        res = val1 == val2
    elif operator == "!=":
        res = val1 == val2
    elif operator == "<=":
        res = val1 <= val2
    elif operator == ">=":
        res = val1 >= val2
    elif operator == "<":
        res = val1 < val2
    elif operator == ">":
        res = val1 > val2
    elif operator == "in":
        res = val1 in val2
    elif operator == "not in":
        res = val1 not in val2
    else:
        raise Exception("Invalid operator: '%s'" % operator)
    if res:
        return options['fn'](this)
    else:
        return options['inverse'](this)

def _fmt_select(this, field_name):
    if not field_name:
        return ""
    obj=None
    try:
        if isinstance(this.context,dict):
            obj=this.context.get('obj')
        elif isinstance(this.context,Scope):
            obj=this.context.context
        else:
            return field_name
        if not obj:
            return field_name
        model=obj._model
        val=obj[field_name]
        return  dict(get_model(model)._fields[field_name].selection)[val]
    except:
        return field_name

def _ifeq(this, options, val1, val2):
    if val1 == val2:
        return options['fn'](this)
    else:
        return options['inverse'](this)

def _if_match(this, options, val, pattern):
    if not val:
        val = ""
    exp = pattern.replace("%", ".*")
    if re.match(exp, val):
        return options['fn'](this)
    else:
        return options['inverse'](this)

_globals_ = {
    'helpers': {
        'blockHelperMissing': _blockHelperMissing,
        'each': _each,
        'if': _if,
        'helperMissing': _helperMissing,
        'unless': _unless,
        'with': _with,
        'compare': _compare,
        'ifeq': _ifeq,
        'if_match': _if_match,
    },
}

def register_helper(name,func):
    _globals_["helpers"][name]=func

def get_helpers():
    return _globals_["helpers"]

class CodeBuilder:

    def __init__(self):
        self.stack = []
        self.blocks = {}

    def start(self):
        self._result = strlist()
        self.stack.append((self._result, "render"))
        self._result.grow("def render(context, helpers=None, partials=None):\n")
        self._result.grow("    result = strlist()\n")
        self._result.grow("    _helpers = dict(_globals_['helpers'])\n")
        self._result.grow("    if helpers is not None: _helpers.update(helpers)\n")
        self._result.grow("    helpers = _helpers\n")
        self._result.grow("    if partials is None: partials = {}\n")

    def finish(self):
        self._result.grow("    return result\n")
        source = "from pyhbs.hbs_compiler import strlist,escape,Scope,partial,_globals_,resolve\n\n"
        for name, lines in reversed(sorted(self.blocks.items())):
            source += "".join(lines) + "\n"
        lines = self._result
        source += "".join(lines)
        return source

    def start_block(self):
        name = "render_block%d" % len(self.blocks)
        self._result = strlist()
        self.blocks[name] = self._result
        self.stack.append((self._result, name))
        self._result.grow("def %s(context, helpers=None, partials=None):\n" % name)
        self._result.grow("    result = strlist()\n")
        self._result.grow("    _helpers = dict(_globals_['helpers'])\n")
        self._result.grow("    if helpers is not None: _helpers.update(helpers)\n")
        self._result.grow("    helpers = _helpers\n")
        self._result.grow("    if partials is None: partials = {}\n")

    def finish_block(self):
        self._result.grow("    return result\n")
        name = self.stack.pop(-1)[1]
        self._result = self.stack and self.stack[-1][0]
        return name

    def add_block(self, symbol, arguments, name, alt_name):
        call = self.arguments_to_call(arguments)
        self._result.grow([
            "    options = {'fn': %s}\n" % name,
            "    options['helpers'] = helpers\n"
            "    options['partials'] = partials\n"
        ])
        if alt_name:
            self._result.grow(["    options['inverse'] = %s\n" % alt_name])
        else:
            self._result.grow([
                "    options['inverse'] = lambda this: None\n"
            ])
        self._result.grow([
            "    value = helper = helpers.get('%s')\n" % symbol,
            "    if value is None:\n"
            "        value = context.get('%s')\n" % symbol,
            "    if helper and callable(helper):\n"
            "        this = Scope(context, context)\n"
            "        value = value(this, options, %s\n" % call,
            "    else:\n"
            "        helper = helpers['blockHelperMissing']\n"
            "        value = helper(context, options, value)\n"
            "    if value is None: value = ''\n"
            "    result.grow(value)\n"
        ])

    def add_literal(self, value):
        self._result.grow("    result.append(%r)\n" % value)

    def _lookup_arg(self, arg):
        if not arg:
            return "context"
        return arg

    def arguments_to_call(self, arguments):
        params = list(map(self._lookup_arg, arguments))
        return ", ".join(params) + ")"

    def find_lookup(self, path, path_type, call):
        if path and path_type == "simple":  # simple names can reference helpers.
            # TODO: compile this whole expression in the grammar; for now,
            # fugly but only a compile time overhead.
            # XXX: just rm.
            realname = path.replace('.get("', '').replace('")', '')
            self._result.grow([
                "    value = helpers.get('%s')\n" % realname,
                "    if value is None:\n"
                "        value = resolve(context, '%s')\n" % path,
            ])
        elif path_type == "simple":
            realname = None
            self._result.grow([
                "    value = resolve(context, '%s')\n" % path,
            ])
        else:
            realname = None
            self._result.grow("    value = %s\n" % path)
        self._result.grow([
            "    if callable(value):\n"
            "        this = Scope(context, context)\n"
            "        value = value(this, %s\n" % call,
        ])
        if realname:
            self._result.grow(
                "    elif value is None:\n"
                "        this = Scope(context, context)\n"
                "        value = helpers.get('helperMissing')(this, '%s', %s\n"
                % (realname, call)
            )
        self._result.grow("    if value is None: value = ''\n")

    def add_escaped_expand(self, path_type_path, arguments):
        (path_type, path) = path_type_path
        call = self.arguments_to_call(arguments)
        self.find_lookup(path, path_type, call)
        self._result.grow([
            "    if type(value) is not strlist:\n",
            "        value = escape(str(value))\n",
            "    result.grow(value)\n"
        ])

    def add_expand(self, path_type_path, arguments):
        (path_type, path) = path_type_path
        call = self.arguments_to_call(arguments)
        self.find_lookup(path, path_type, call)
        self._result.grow([
            "    if type(value) is not strlist:\n",
            "        value = str(value)\n",
            "    result.grow(value)\n"
        ])

    def _debug(self):
        self._result.grow("    import pdb;pdb.set_trace()\n")

    def add_invertedblock(self, symbol, arguments, name):
        self._result.grow([
            "    value = context.get('%s')\n" % symbol,
            "    if not value:\n"
            "    "])
        self._invoke_template(name, "context")

    def _invoke_template(self, fn_name, this_name):
        self._result.grow([
            "    result.grow(",
            fn_name,
            "(",
            this_name,
            ", helpers=helpers, partials=partials))\n"
        ])

    def add_partial(self, symbol, arguments):
        if arguments:
            assert len(arguments) == 1, arguments
            arg = arguments[0]
        else:
            arg = ""
        self._result.grow([
            "    inner = partials['%s']\n" % symbol,
            "    scope = Scope(%s, context)\n" % self._lookup_arg(arg)])
        self._invoke_template("inner", "scope")

class Compiler:
    _handlebars = OMeta.makeGrammar(handlebars_grammar, {}, 'handlebars')
    _builder = CodeBuilder()
    _compiler = OMeta.makeGrammar(compile_grammar, {'builder': _builder})

    def __init__(self):
        self._helpers = {}

    def compile(self, source):
        self._builder.stack = []
        self._builder.blocks = {}
        tree, err = self._handlebars(source).apply('template')
        if err.error:
            raise Exception(err.formatError(source))
        code, err = self._compiler(tree).apply('compile')
        if err.error:
            raise Exception(err.formatError(tree))
        return code
