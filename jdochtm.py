import copy
from typing import Dict, NamedTuple, List, Tuple, Union
from bs4 import BeautifulSoup

def lower_first(text: str) -> str:
    return text[:1].lower() + text[1:]

TO_ATTRIB = {"parameters": "parameter"}

def desc_group(children: List) -> List[Tuple[str, str]]:
    print(f"{children=}")
    if children == None: return []

    attribs = []
    current_datatag = None
    for element in children:
        if element.name == None: continue
        if element.name == "dt":
            current_datatag = lower_first(element.text)
            current_datatag = current_datatag.replace(":", "")
            current_datatag = TO_ATTRIB.get(current_datatag, current_datatag)
            print(f"{current_datatag=}")
        elif element.name == "dd":
            if current_datatag == None:
                raise ValueError("Incorrect format for a datalist")
            # NOTE: just to clean this up I will remove the - , thing
            attribs.append((current_datatag, element.text.replace("\xa0", " ").replace(" - , ", " - ")))

    print(f"{attribs=}")
    return attribs

# [access_modifier] [static] [return_type] [name] ([parameters & types]) ;
class ClassMethod(NamedTuple):
    name: str
    modifier: str
    is_static: bool
    return_type: str
    # body: str
    parameters_types: List[Tuple[str, str]]

    javadocstr: str

    annotations: List[Tuple[str, str]] = []
    inferred_body: str = ""

# [access_modifier] [static] [final] [type] [name] [= initial value] ;
class ClassField(NamedTuple):
    name: str
    modifier: str
    is_static: bool
    is_final: bool
    field_type: str

    javadocstr: str

class JavaDoc(NamedTuple):
    class_name: str
    methods: List[ClassMethod]
    fields: List[ClassField]
    extends: str = ""
    implements: List[str] = []

BUILT_IN_METHODS = ["toString", "equals"]

def parse_field(field_node) -> ClassField:
    signature_parts = field_node.select_one("div[class=\"member-signature\"]").text.split("\xa0")
    divs = list(field_node.select('div'))

    field_desc = ""
    if len(divs) > 1:
        field_desc = divs[-1].text

    return ClassField(signature_parts[-1], signature_parts[0], "static" in signature_parts, "final" in signature_parts, signature_parts[-2], field_desc)

def parse_method(method_node) -> ClassMethod:
    whole_signature = method_node.select_one("div[class=\"member-signature\"]").text
    first_half, parameters = whole_signature.split("(")
    assert parameters[-1] == ")", "Method signature should end with closing parenthesis"
    parameters = parameters[:-1]
    if parameters == "":
        parameters = []
    else:
        parameters = [(parampair.split("\xa0")[0], parampair.split("\xa0")[1]) for parampair in parameters.split(",")]

    signature_parts = first_half.split("\xa0")
    method_name = signature_parts[-1]

    divs = list(method_node.select('div'))
    if len(divs) > 1:
        field_desc = divs[-1].text

    annotation = method_node.select_one("dl[class=\"notes\"]")
    annotations = desc_group(annotation)

    return ClassMethod(method_name, signature_parts[0], "static" in signature_parts, signature_parts[-2], parameters, field_desc, annotations)

def parse_from_html(html_obj, infer_method = True) -> JavaDoc:
    document = BeautifulSoup(html_obj, features="lxml")
    class_name = document.select_one("h1[class=\"title\"]").text

    extends_implements = document.select_one("span[class=\"extends-implements\"]")
    extends_implements = extends_implements.text.replace("\n", " ")
    parts = extends_implements.split(" implements ")
    extends = parts[0][len("extends "):]
    if extends == "Object": extends = ""
    implements = []
    # print(f"{extends=}")
    if len(parts) > 1:
        implements = parts[1].split(", ")

    assert class_name.startswith("Class "), "Class name should have started with 'Class '"

    class_name = class_name[len("Class "):]

    # parse all fields
    field_objs = document.select("section[class=\"field-details\"] > ul > li > section[class=\"detail\"]")
    if field_objs == None: field_objs = []
    class_fields = list(map(parse_field, field_objs))

    # parse all methods
    method_objs = document.select("section[class=\"method-details\"] > ul > li > section[class=\"detail\"]")
    if method_objs == None: method_objs = []
    class_methods = list(map(parse_method, method_objs))

    if infer_method:
        new_class_methods = []
        for class_method in class_methods:
            new_class_method = class_method
            if class_method.name.startswith("get"):
                inferred_varname = lower_first(class_method.name[len("get"):])
                print(f"Get {inferred_varname} should be {class_method.return_type}")

                matching_types = filter(lambda x: x.field_type == class_method.return_type, class_fields)
                matching = list(filter(lambda x: x.name.lower() == inferred_varname.lower(), matching_types))
                if len(matching) > 0:
                    print(f"found {matching}, picking first!")

                    if not class_method.is_static:
                        new_class_method = class_method._replace(inferred_body = f"return this.{matching[0].name};")
                    else:
                        new_class_method = class_method._replace(inferred_body = f"return {matching[0].name};")
                else:
                    # new_class_method = class_method
                    new_class_method = class_method._replace(inferred_body = f"// WARNING: Couldn't exact match!!!\n    return this.{inferred_varname};")
            elif class_method.name.startswith("set") and len(class_method.parameters_types) == 1:
                inferred_varname = lower_first(class_method.name[len("set"):])
                print(f"Set {inferred_varname} should be {class_method.return_type}")

                ptype, pname = class_method.parameters_types[0]
                matching_types = filter(lambda x: x.field_type == ptype, class_fields)
                matching = list(filter(lambda x: x.name.lower() == inferred_varname.lower(), matching_types))
                if len(matching) > 0:
                    print(f"found {matching}, picking first!")

                    if not class_method.is_static:
                        new_class_method = class_method._replace(inferred_body = f"this.{matching[0].name} = {pname};")
                    else:
                        new_class_method = class_method._replace(inferred_body = f"return {matching[0].name} = {pname};")
                else:
                    if not class_method.is_static:
                        new_class_method = new_class_method = class_method._replace(inferred_body = f"// WARNING: Couldn't exact match!!!\n    this.{matching[0].name} = {pname};")
                    else:
                        new_class_method = new_class_method = class_method._replace(inferred_body = f"// WARNING: Couldn't exact match!!!\n    {matching[0].name} = {pname};")

            else: new_class_method = class_method
            new_class_methods.append(new_class_method)
        class_methods = new_class_methods
        
    return JavaDoc(class_name, class_methods, class_fields, extends, implements)

def gen_stub(jdoc: JavaDoc) -> str:
    text = f"public class {jdoc.class_name}{' extends ' + jdoc.extends if jdoc.extends != '' else ''}{' implements ' + ', '.join(jdoc.implements) if len(jdoc.extends) > 0 else ''} {{\n"
    for field in jdoc.fields:
        if field.javadocstr != "":
            jdocannotation = '\n  //'.join(field.javadocstr.split('\n'))
            text += f"  // {jdocannotation}\n"
        
        text += f"  {field.modifier}{' final' if field.is_final else ''}{' static' if field.is_static else ''} {field.field_type} {field.name};\n"
    text += "\n"

    for method in jdoc.methods:
        methodcomments = copy.copy(method.javadocstr.split('\n'))

        for jdocattrib in method.annotations:
            name, val = jdocattrib
            if name in ["parameter", "returns", "throws"]:
                methodcomments.append(f" @{name} {val}")
            
        if len(methodcomments) > 0:
            jdocannotation = '\n   * '.join(methodcomments)
            text += f"  /** {jdocannotation}\n   */\n"
        
        text += f"  {method.modifier}{' static' if method.is_static else ''} {method.return_type} {method.name}({' '.join([sub_val for vals in method.parameters_types for sub_val in vals])}) {{\n"
        text += f"    //TODO: Implement me\n"
        if method.inferred_body != "":
            text += f"    {method.inferred_body}\n"
        text += "  }\n\n"
    
    text += "}"
    return text

with open("room.html", "rt") as f:
    print(f"{parse_from_html(f)=}")
    parse_from_html(f)
    print(gen_stub(parse_from_html(f)))