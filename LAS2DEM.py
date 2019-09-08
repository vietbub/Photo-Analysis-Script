import os, subprocess as sub, glob, sys, time
from ext_tools import *

#global paths
lastools_dir = "./programs/lastools/bin/"
saga_dir = './programs/saga/' #I need to fix a spacing issue, make sure this path is available globally for now...

debug = False

def las2dem(lasfiles,grid_template,grid_out):

	lasfiles = lasfiles.replace("\\","/")
	lasdir = fileparts(lasfiles)[0]
	tiletemp = lasdir+"tmp"
	
	bufsize = 1 #line buffered
	log = open(lasdir+"las2dem_log.txt","w",bufsize)

	#get template params
	template_params = get_grid_params(grid_template)
	res_g = float(template_params["CELLSIZE"]) #get cellsize from template
	res_t = res_g/10.0

	#create temp directory
	if not os.path.exists(tiletemp):
		os.makedirs(tiletemp)
		
	num_processes = 6
	
	print "\nTemplate has resolution of " + str(res_g) + ". Starting Processing."
	t = time.time()

	#TILING
	tile_size = res_t * 2250 #after thinning, this will leave tiles at a 150mb size (suggest to keep under 2250 for lincensing...)
	print "(1/" + str(num_processes) + ") Tiling with size " + str(tile_size) + "...",
	#create a tile dir
	tiledir = tiletemp+"/tiles"
	if not os.path.exists(tiledir):
		os.makedirs(tiledir)
	#create command and execute
	cmd = lastools_dir + "lastile -i " + lasfiles + " -odir " + tiledir + " -tile_size " + str(tile_size)
	
	#Test for debugging mode
	if debug:
		log.write(cmd)
	else:
		p = sub.Popen(cmd, stdout=log, stderr=log)
		p.wait()
		
	dt = time.time()-t
	print "Done. Took " + str(dt) + " seconds."
	t = time.time()

	#THINNING
	print "(2/" + str(num_processes) + ") Thinning using resolution " + str(res_t) + "...",
	thindir = tiletemp+"/thinned"
	if not os.path.exists(thindir):
		os.makedirs(thindir)
	#create command and execute
	cmd = lastools_dir + "lasthin -i " + tiledir + "/*.las -odir " + thindir + " -step " + str(res_t) + " -random"
	
	#Test for debugging mode
	if debug:
		log.write(cmd)
	else:
		p = sub.Popen(cmd, stdout=log, stderr=log)
		p.wait()
	
	dt = time.time()-t
	print "Done. Took " + str(dt) + " seconds."
	t = time.time()

	#DENOISE
	print "(3/" + str(num_processes) + ") Stat filter using " + str(res_g) + " search radius and " + str(25) + " neighbors...",
	denoisedir = tiletemp+"/filtered"
	if not os.path.exists(denoisedir):
		os.makedirs(denoisedir)
	#create command and execute
	cmd = lastools_dir + "lasnoise -i " + thindir + "/*.las -odir " + denoisedir + " -step " + str(res_g) + " -isolated 25 -remove_noise"
	
	#Test for debugging mode
	if debug:
		log.write(cmd)
	else:
		p = sub.Popen(cmd, stdout=log, stderr=log)
		p.wait()
	
	dt = time.time()-t
	print "Done. Took " + str(dt) + " seconds."
	t = time.time()
	
	#clean up
	print "Cleaning up temporary files..."
	deletefiles = glob.glob(tiledir+"/*.las") + glob.glob(thindir+"/*.las")
	
	#progress bar
	steps = len(deletefiles)/10
	i=0
	print "Starting [          ]",
	print '\b'*12,
	sys.stdout.flush()
	
	for f in deletefiles:
		os.remove(f)
		
		#progress bar
		if i%steps == 0:
			print '\b.',
			sys.stdout.flush()
		i+=1
	
	os.rmdir(tiledir)
	os.rmdir(thindir)
	
	dt = time.time()-t
	print "\b]  Done. Took " + str(dt) + " seconds."
	t = time.time()
	
	########################
	#SAGA
	#convert to spc
	print "(4/" + str(num_processes) + ") Converting files..."
	lasfiles = glob.glob(denoisedir + "/*.las")
	
	#progress bar
	steps = len(lasfiles)/10
	i=0
	print "Starting [          ]",
	print '\b'*12,
	sys.stdout.flush()
	
	for lasfile in lasfiles:
		cmd = "saga_cmd io_shapes_las \"Import LAS Files\" -FILES " + lasfile + " -POINTS " + lasfile[:-4] + ".spc"
			
		#Test for debugging mode
		if debug:
			log.write(cmd)
		else:
			p = sub.Popen(cmd, stdout=log, stderr=log)
			p.wait()
		
		#progress bar
		if i%steps == 0:
			print '\b.',
			sys.stdout.flush()
		i+=1
	dt = time.time()-t
	print "\b]  Done. Took " + str(dt) + " seconds."
	t = time.time()
		
	#gridding
	print "\n(5/" + str(num_processes) + ") Gridding using mean..."
	pcfiles = glob.glob(denoisedir + "/*.spc")
	
	#pt density output
	ptdendir = denoisedir+"/ptden"
	if not os.path.exists(ptdendir):
		os.makedirs(ptdendir)
	
	#progress bar
	steps = len(pcfiles)/10
	i=0
	print "Starting [          ]",
	print '\b'*12,
	sys.stdout.flush()
	
	for pcfile in pcfiles:
		d,pcfilename = fileparts(pcfile)
		cmd = 'saga_cmd grid_gridding "Shapes to Grid" -INPUT ' + pcfile + ' -FIELD "Z" -MULTIPLE 4 -TARGET_DEFINITION 1 -TARGET_TEMPLATE ' + grid_template + ' -TARGET_OUT_GRID ' + pcfile[:-4] + ".sgrd -TARGET_COUNT " + ptdendir + "/" + pcfilename[:-4] + ".sgrd"
			
		#Test for debugging mode
		if debug:
			log.write(cmd)
		else:
			p = sub.Popen(cmd, stdout=log, stderr=log)
			p.wait()
			
		#progress bar
		if i%steps == 0:
			print '\b.',
			sys.stdout.flush()
		i+=1
	dt = time.time()-t
	print "\b]  Done. Took " + str(dt) + " seconds."
	t = time.time()
		
	#mosiacking
	print "(6/" + str(num_processes) + ") Mosiacking grid files...",
	
	#DEM files
	grdfiles = glob.glob(denoisedir + "/*.sgrd")
	GRIDS = ''
	for f in grdfiles:
		GRIDS = GRIDS + f + ';'
	GRIDS = GRIDS[:-1]
	cmd = 'saga_cmd grid_tools "Mosaicking" -GRIDS ' + GRIDS + ' -TYPE=7 -INTERPOL=0 -OVERLAP=4 -MATCH=0 -TARGET_TEMPLATE ' + grid_template + ' -TARGET_OUT_GRID ' + grid_out
	
	#Test for debugging mode
	if debug:
		log.write(cmd)
	else:
		p = sub.Popen(cmd, stdout=log, stderr=log)
		p.wait()
	
	
	#Pt files
	grdfiles = glob.glob(ptdendir + "/*.sgrd")
	GRIDS = ''
	for f in grdfiles:
		GRIDS = GRIDS + f + ';'
	GRIDS = GRIDS[:-1]
	cmd = 'saga_cmd grid_tools "Mosaicking" -GRIDS ' + GRIDS + ' -TYPE=7 -INTERPOL=0 -OVERLAP=0 -MATCH=0 -TARGET_USER_FITS=1 -TARGET_TEMPLATE ' + grid_template + ' -TARGET_OUT_GRID ' + grid_out[:-5] + "_PT.sgrd"
	
	#Test for debugging mode
	if debug:
		log.write(cmd)
	else:
		p = sub.Popen(cmd, stdout=log, stderr=log)
		p.wait()
	
	dt = time.time()-t
	print "Done. Took " + str(dt) + " seconds."
	t = time.time()
	
	log.close()

#main
if len(sys.argv) != 4:
	print 'usage: python LAS2DEM.py <in:/path/to/lasfiles> <in:/path/to/template> <out:/path/to/dem.sgrd>'
else:
	lasfiles = sys.argv[1]
	grid_template = sys.argv[2]
	grid_out = sys.argv[3]

	#print lasfiles,grid_template,grid_out
	las2dem(lasfiles,grid_template,grid_out)