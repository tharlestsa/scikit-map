from pyeumap import datasets
from pyeumap.parallel import ThreadGeneratorLazy, ProcessGeneratorLazy
import geopandas as gpd
import multiprocessing
from osgeo import osr
import rasterio
from rasterio.windows import Window, from_bounds
import os.path

from .misc import ttprint

EUMAP_TILING_SYSTEM_FN = 'eu_tilling system_30km.gpkg'

class TilingProcessing():
	
	def __init__(self, tiling_system_fn = None, 
				 base_raster_fn = None,
				 verbose:bool = True):
		
		if tiling_system_fn is None:
			
			if verbose:
				ttprint('Using default eumap tiling system')

			tiling_system_fn = f'eumap_data/{EUMAP_TILING_SYSTEM_FN}'
			if not os.path.isfile(tiling_system_fn):
				datasets.get_data(EUMAP_TILING_SYSTEM_FN)

		self.tiles = gpd.read_file(tiling_system_fn)
		self.num_tiles = self.tiles.shape[0]
		self.base_raster = rasterio.open(base_raster_fn)

		tiles_srs = osr.SpatialReference()
		tiles_srs.ImportFromProj4(self.tiles.crs.to_proj4())
		base_raster_srs = osr.SpatialReference()
		base_raster_srs.ImportFromProj4(self.base_raster.crs.to_proj4())
		
		if not (tiles_srs.ExportToProj4() == base_raster_srs.ExportToProj4()):
			raise Exception('Different SpatialReference' +
						f'\n tiling_system_fn ({tiles_srs.ExportToProj4()})'+
						f'\n base_raster_fn ({base_raster_srs.ExportToProj4()})')
		if verbose:
			ttprint(f'{self.num_tiles} tiles available')
		
	def process_one(self, idx, func, func_args = ()):
		
		tile = self.tiles.iloc[idx]
		left, bottom, right, top = tile.geometry.bounds
		window = from_bounds(left, bottom, right, top, self.base_raster.transform)
				
		return func(idx, tile, window, *func_args)
	
	def process_multiple(self, idx_list, func, func_args = (), 
		max_workers:int = multiprocessing.cpu_count(),
		use_threads:bool = True):
		
		args = []
		for idx in idx_list:
			tile = self.tiles.iloc[idx]
			
			xoff = tile[self.col_xoff]
			yoff = tile[self.col_yoff]
			
			window = Window(xoff, yoff, self.xsize, self.ysize)
			
			args.append((idx, tile, window))
		
		WorkerPool = (ThreadGeneratorLazy if use_threads else ProcessGeneratorLazy)

		results = []
		for r in WorkerPool(func, iter(args), fixed_args=func_args, max_workers=max_workers, chunk=max_workers*2):
			results.append(r)

		return results

	def process_all(self, func, func_args = (), 
		max_workers:int = multiprocessing.cpu_count(),
		use_threads:bool = True):
	
		idx_list = range(0, self.num_tiles)
		return self.process_multiple(idx_list, func, func_args, max_workers, use_threads)
