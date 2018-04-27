from . import hbs_compiler

#Benefit for runtime
_template_cache={}

class Template(object):
    pass

def register_helper(name,func):
    hbs_compiler.register_helper(name,func)

def get_template_src(file_path):
    try:
        f = open(file_path,"r")
        tmpl = f.read()
    except Exception as e:
        print("Template file path:")
        print(file_path)
        raise Exception("Failed to compile template: %s" % file_path)
        
    return tmpl

def get_template(file_path):
    tmpl=_template_cache.get(file_path)
    if tmpl:
        return tmpl
    tmpl_src = get_template_src(file_path)
    try:
        compiler = hbs_compiler.Compiler()
        py_src = compiler.compile(tmpl_src)
        tmpl = Template()
        exec(py_src, tmpl.__dict__)
    except Exception as e:
        print("Template source:")
        print(tmpl_src)
        raise Exception("Failed to compile template: %s" % file_path)
    _template_cache[file_path] = tmpl
    return tmpl

def render_file(file_path, context, data={}):
    tmpl = get_template(file_path)
    scope = hbs_compiler.Scope(context,context,data=data)
    result = "".join(tmpl.render(scope))
    return result

def render_source(tmpl_src, context, data={}):
    tmpl = None
    try:
        compiler = hbs_compiler.Compiler()
        py_src = compiler.compile(tmpl_src)
        tmpl = Template()
        exec(py_src, tmpl.__dict__)
    except Exception as e:
        print("ERROR - Template source:")
        print(tmpl_src)
    scope = hbs_compiler.Scope(context,context,data=data)
    result = "".join(tmpl.render(scope))
    return result
