del *.hdf
copy key.bin  hdfbin-3-006000.raw
HDFTOOL c hdfbin-1-006000.raw -id1=0000.0000 -id2=0076.0600 key.hdf
del *.raw
