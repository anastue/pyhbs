# pyhbs - Handlebars.js for Python 3

[![Build Status](https://travis-ci.org/anastue/pyhbs.svg?branch=master)](https://travis-ci.org/wbond/pybars3)

Pyhbs : Handlebars template compiler for Python 3.
It is a fork of the pybars project.
* Make it simple.
* Easy to use.
* No dependency.
* Make it faster.

## Installation

```bash
pip install pyhbs
```


## Usage

see more at http://handlebarsjs.com.

Typical usage:

```python
from pyhbs import render_file, render_source, register_helper

#DATA
#vals=[{"number":i, "name": "NUMBER %s"%i} for i in range(1,4)]
vals=[
    {
        "number" : 1,
        "name" : "Number 1",
    }, {
        "number" : 2,
        "name" : "Number 2",
    }, {
        "number" : 3,
        "name" : "Number 3",
    }
]
data = {
    "name" : "Anas",
    "data" : vals,
    "obj" : {"foo" : "bar", "price" : 40}
}

def sample_template():
    print("render.file")
    #Target of template
    path_file = "templates/test.hbs" 
    #path_file = "templates/test.txt" or any file types
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

#Add Helper

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

```

### Handlers

Translate like JS version.

* block helpers should accept `this, options, *args, **kwargs`
* other helpers should accept `this, *args, **kwargs`
* closures in the context should accept `this, *args, **kwargs`

## Dependencies

* Python 3.3+


## Todo

- [ ] TEST
