! MIDAS script to be place in midwork of the FEROS-DRS
! Full night reduction with options to use optimum extraction
! @ Regis Lachaume 2014-2017

! Command line arguments
crossref reduce extmode prepare calibrate lamp guess threshold range 
define/par p1 LFSO     C "Catalogues to reduce exposures of [LFSO]"
define/par p2 O        C "Extraction method [O]"
define/par p3 Y        C "Prepare catalogues [Y]"
define/par p4 Y        C "Perform calibration with specified lamp [Y]"
define/par p5 ThArNe   C "Wavelength calibration image catalogue [ThArNe]: "
define/par p6 ThAr9021 C "Name of guess session [ThAr9021]: "
define/par p7 0.85     N "Threshold [0.85]: "
define/par p8 0.0,0.0  C "Automatic threshold search range [0.0,0.0]: "

! Help
if "{p1}" .eq. "help" then
  write/out @@ donight reduce=LFSO extmode=O makecats=Y calibrate=Y lamp=ThArNe guess=ThAr9021 threshold=0.85 range=0.0,0.0 
  write/out 
  write/out "Reduce a full night, with possible calibration on the spot."
  return
endif

def/loc reduce/c/1/4 "{p1}" " " 
def/loc extmode/c/1/1 "{p2}"
def/loc prepare/c/1/1 "{p3}"
def/loc calibrate/c/1/1 "{p4}"
def/loc lamp/c/1/20 "{p5}"
def/loc guess/c/1/20 "{p6}"
def/loc threshold/c/1/20 "{p7}"
def/loc range/c/1/20 "{p8}"

! Dark substraction
write/key dark/c/1/1 "N"
write/key ExtrNonFFSpec/c/1/1 "Y"
write/key symMkExtdFITS/c/1/1 "N"

! Initialisation 
if "{prepare}" .eq. "Y" then
  @@ prepare
endif

if "{calibrate}" .eq. "Y" then
  @@ init {guess} start {threshold} N {range} FF.cat {lamp}.cat 39
else
  @@ Init-DEFAULT
endif

! Extraction method
! set/feros EXT_MODE="{p5}"
! write/key def_extmode/c/1/1 "M"
set/feros EXT_MODE="B"
write/key def_extmode/c/1/1 "B"
set/feros MERGE_MTD="N"

write/out "{p5}"

def/loc i/i/1/1 0
do i = 1 4
  if  reduce({i}:{i}) .eq. "O" then
    @@ autoreduce_cat Objects.cat
  endif
  if reduce({i}:{i}) .eq. "L" then
    @@ autoreduce_cat {p4}.cat
  endif
  if reduce({i}:{i}) .eq. "F" then
    @@ autoreduce_cat FF.cat
  endif
  if reduce({i}:{i}) .eq. "S" then
    @@ autoreduce_cat std.cat
    @@ autoreduce_cat sol.cat
  endif
enddo
