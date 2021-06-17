import geopandas as gpd
import multiprocessing
from osgeo import osr
import math
import rasterio
from rasterio.windows import Window, from_bounds
import os.path
from pqdm.processes import pqdm as ppqdm
from pqdm.threads import pqdm as tpqdm

from .misc import ttprint
from . import datasets
from .parallel import ThreadGeneratorLazy, ProcessGeneratorLazy

EUMAP_TILING_SYSTEM_FN = 'eu_tilling system_30km.gpkg'

class TilingProcessing():

	def __init__(self, tiling_system_fn = None,
				 base_raster_fn = None,
				 pixel_precision = 6,
				 verbose:bool = True):

		if tiling_system_fn is None:

			if verbose:
				ttprint('Using default eumap tiling system')

			tiling_system_fn = f'eumap_data/{EUMAP_TILING_SYSTEM_FN}'
			if not os.path.isfile(tiling_system_fn):
				datasets.get_data(EUMAP_TILING_SYSTEM_FN)

		self.pixel_precision = pixel_precision
		self.tiles = gpd.read_file(tiling_system_fn)
		self.num_tiles = self.tiles.shape[0]
		self.base_raster = rasterio.open(base_raster_fn)

		tiles_srs = osr.SpatialReference()
		tiles_srs.ImportFromProj4(self.tiles.crs.to_proj4())
		base_raster_srs = osr.SpatialReference()
		base_raster_srs.ImportFromProj4(self.base_raster.crs.to_proj4())

		if base_raster_srs.ImportFromProj4(self.base_raster.crs.to_proj4()) != tiles_srs.ImportFromProj4(self.tiles.crs.to_proj4()):
			raise Exception('Different SpatialReference' +
						f'\n tiling_system_fn ({tiles_srs.ExportToProj4()})'+
						f'\n base_raster_fn ({base_raster_srs.ExportToProj4()})')
		if verbose:
			ttprint(f'{self.num_tiles} tiles available')

	def process_one(self, idx, func, func_args = ()):

		tile = self.tiles.iloc[idx]
		left, bottom, right, top = tile.geometry.bounds

		# Pay attetion here, because it can change the size of the tile
		window = from_bounds(left, bottom, right, top, self.base_raster.transform) \
							.round_lengths(op='floor', pixel_precision=self.pixel_precision)

		return func(idx, tile, window, *func_args)

	def process_multiple(self, idx_list, func, func_args = (),
		max_workers:int = multiprocessing.cpu_count(),
		use_threads:bool = True,
		progress_bar:bool = True):
		print(f"func_args: {func_args}")
		args = []
		for idx in idx_list:
			tile = self.tiles.iloc[idx]
			left, bottom, right, top = tile.geometry.bounds

			# Pay attention here, because it can change the size of the tile
			window = from_bounds(left, bottom, right, top, self.base_raster.transform) \
								.round_lengths(op='floor', pixel_precision=self.pixel_precision)

			args.append((idx, tile, window, *func_args))
		if progress_bar:
			pqdm = (tpqdm if use_threads else ppqdm)
			results = pqdm(args,func,n_jobs=max_workers,argument_type='args')

		else:
			WorkerPool = (ThreadGeneratorLazy if use_threads else ProcessGeneratorLazy)

			results = []
			for r in WorkerPool(func, iter(args), max_workers=max_workers, chunk=max_workers*2):
				results.append(r)

		return results

	def process_all(self, func, func_args = (),
		max_workers:int = multiprocessing.cpu_count(),
		use_threads:bool = True):

		idx_list = range(0, self.num_tiles)
		return self.process_multiple(idx_list, func, func_args, max_workers, use_threads)