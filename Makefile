PYTHONPATH=${HOME}/python
EXECPATH=${HOME}/bin

install:
	mkdir -p ${PYTHONPATH}/MPG
	cp *.py ${PYTHONPATH}/MPG
	cp exec/* ${EXECPATH}
