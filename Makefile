PYTHONPATH=${HOME}/python
EXECPATH=${HOME}/bin
MPGFILES=esoarchive.py programlist.py  utils.py esolog.py getesomail.py schedule.py


install:
	mkdir -p ${PYTHONPATH}/MPG
	cp gtable.py ${PYTHONPATH}
	cp ${MPGFILES} ${PYTHONPATH}/MPG
	cp exec/* ${EXECPATH}
