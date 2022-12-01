import argparse
import pdfx
import re
import os
from pathlib import Path
import sys

print(f"{Path(os.path.realpath(__file__)).parent=}")

is_javadoc = re.compile(r"javadocs\/.*\.html", re.MULTILINE)

parser = argparse.ArgumentParser(prog = 'shw')
parser.add_argument('file', help='pdf file')
args = parser.parse_args()

pdf = pdfx.PDFx(args.file)
urls = pdf.get_references_as_dict()["url"]
javadoc_urls = [url for url in urls if is_javadoc.search(url) != None and not url.endswith("allclasses-index.html")]

[os.system(f"{sys.executable} {(Path(os.path.realpath(__file__)).parent / 'jstem.py').absolute()} {jurl}") for jurl in javadoc_urls]