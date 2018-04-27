#!/usr/bin/env python3

from pyhbs import render_file, render_source, register_helper

#DATA
vals=[{"number":i, "name": "NUMBER %s"%i} for i in range(1,10)]
data = {
    "name" : "Anas",
    "data" : vals,
    "obj" : {"foo" : "bar", "price" : 40}
}

def sample_template():
    print("render.file")
    #Target of template
    path_file = "templates/test.hbs" 
    #path_file = "templates/test.txt"
    output = render_file(path_file, data)
    print(output)

def sample_source():
    print("render.source")
    source = '''
        {{#list data}}{{number}} : {{name}}{{/list}}
        {{name}} : {{currency obj.price}}
    '''
    output = render_source(source, data)
    print(output)

#Add Helper : currency
def _currency(this, context, nogroup=False, zero=None, scale="2"):
    if context is None:
        return ""
    try:
        val = float(context)  # in case string
        if zero is not None and abs(val) < 0.0001:
            return zero
        type_format = "{:0,.%sf}"%scale
        val = type_format.format(val)
        if nogroup:
            val = val.replace(",", "")
        return val
    except:
        return ""

#EX : {{currency [number]}}
register_helper("currency", _currency)

def _list(this, options, items):
    result = [u'<ul>']
    for thing in items:
        result.append(u'<li>')
        result.extend(options['fn'](thing))
        result.append(u'</li>')
    result.append(u'</ul>')
    return result

register_helper("list", _list)

if __name__=="__main__":
    sample_template()
    sample_source()
