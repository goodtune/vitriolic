TARGETS=custom.css
LESSC=lessc -x

all: $(TARGETS)

%.css: %.less
	$(LESSC) $< > $@
