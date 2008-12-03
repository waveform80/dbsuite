# vim: set noet sw=4 ts=4:

# External utilities
PYTHON=python
PYFLAGS=
#LYNX=lynx
#LYNXFLAGS=-nonumbers -justify
LYNX=links
LYNXFLAGS=-no-numbering -no-references

# Calculate the base name of the distribution, the location of all source files
# and documentation files
NAME:=$(shell $(PYTHON) $(PYFLAGS) setup.py --name)
BASE:=$(shell $(PYTHON) $(PYFLAGS) setup.py --fullname)
SRCS:=$(shell \
	$(PYTHON) $(PYFLAGS) setup.py egg_info >/dev/null 2>&1 && \
	cat $(NAME).egg-info/SOURCES.txt)
DOCS:=README.txt TODO.txt

# Calculate the name of all distribution archives / installers
EGG=dist/$(BASE).egg
WININST=dist/$(BASE).win32.exe
RPMS=dist/$(BASE)-1.noarch.rpm dist/$(BASE)-1.src.rpm
SRCTAR=dist/$(BASE).tar.gz
SRCZIP=dist/$(BASE).zip

# Default target
build:
	$(PYTHON) $(PYFLAGS) setup.py build

install:
	$(PYTHON) $(PYFLAGS) setup.py install

test:
	echo No tests currently implemented
	#cd examples && ./runtests.sh

clean:
	$(PYTHON) $(PYFLAGS) setup.py clean
	rm -f $(DOCS) tags
	rm -fr build/ $(NAME).egg-info/

cleanall: clean
	rm -fr dist/

dist: bdist sdist

bdist: $(WININST) $(RPMS) $(EGG)

sdist: $(SRCTAR) $(SRCZIP)

$(EGG): $(SRCS) $(DOCS)
	$(PYTHON) $(PYFLAGS) setup.py bdist --formats=egg

$(WININST): $(SRCS) $(DOCS)
	$(PYTHON) $(PYFLAGS) setup.py bdist --formats=wininst

$(RPMS): $(SRCS) $(DOCS)
	$(PYTHON) $(PYFLAGS) setup.py bdist --formats=rpm

$(SRCTAR): $(SRCS) $(DOCS)
	$(PYTHON) $(PYFLAGS) setup.py sdist --formats=gztar

$(SRCZIP): $(SRCS) $(DOCS)
	$(PYTHON) $(PYFLAGS) setup.py sdist --formats=zip

tags: FORCE
	ctags -R --exclude="build/*"

README.txt: FORCE
	echo "Generated from the db2makedoc wiki at:" > README.txt
	echo "http://faust.hursley.uk.ibm.com/trac/db2makedoc/wiki/" >> README.txt
	for page in Requirements InstallWindows InstallLinux Tutorial; do \
		$(LYNX) $(LYNXFLAGS) -dump http://faust.hursley.uk.ibm.com/trac/db2makedoc/wiki/$$page | awk '\
			BEGIN {printing=0;} \
			/^ *\* Last Change *$$/ {printing=1; next;} \
			/^ *Terms of use *$$/ {printing=0;} \
			{if (printing) print;}' >> README.txt; done

TODO.txt: FORCE
	echo "Generated from the db2makedoc wiki at:" > TODO.txt
	echo "http://faust.hursley.uk.ibm.com/trac/db2makedoc/wiki/" >> TODO.txt
	$(LYNX) $(LYNXFLAGS) -dump http://faust.hursley.uk.ibm.com/trac/db2makedoc/wiki/KnownIssues | awk '\
		BEGIN {printing=0;} \
		/^ *\* Last Change *$$/ {printing=1; next;} \
		/^ *Terms of use *$$/ {printing=0;} \
		{if (printing) print;}' >> TODO.txt; done

FORCE:
