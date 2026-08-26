import ee
import geemap
import json
import os


# Initialize Google Earth Engine
ee.Initialize(project='indigo-terra-471402-m8')


def get_aoi(lat, lon, buffer_km=25):
    """
    Build a square Area of Interest around a point.
    """
    point = ee.Geometry.Point([lon, lat])
    return point.buffer(buffer_km * 1000).bounds()


def get_sentinel1_collection(aoi, start_date, end_date):
    """
    Find Sentinel-1 SAR images covering the AOI.
    """
    return (
        ee.ImageCollection('COPERNICUS/S1_GRD')
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.eq('instrumentMode', 'IW'))
        .filter(
            ee.Filter.listContains(
                'transmitterReceiverPolarisation',
                'VV'
            )
        )
        .filter(
            ee.Filter.listContains(
                'transmitterReceiverPolarisation',
                'VH'
            )
        )
    )


def select_closest_image(collection, target_date):
    """
    Return the Sentinel-1 image closest to the requested date.
    """
    target = ee.Date(target_date)

    def add_time_diff(image):
        diff = ee.Number(
            image.date().difference(target, 'day')
        ).abs()

        return image.set('date_diff', diff)

    return (
        collection
        .map(add_time_diff)
        .sort('date_diff')
        .first()
    )


def get_scene_metadata(image, aoi):
    """
    Extract important metadata from the selected scene.
    """

    return {
        'image_id': image.get(
            'system:index'
        ).getInfo(),

        'date': ee.Date(
            image.get('system:time_start')
        ).format('YYYY-MM-dd').getInfo(),

        'platform': image.get(
            'platform_number'
        ).getInfo(),

        'orbit_direction': image.get(
            'orbitProperties_pass'
        ).getInfo(),

        'instrument_mode': image.get(
            'instrumentMode'
        ).getInfo(),

        'polarizations': image.get(
            'transmitterReceiverPolarisation'
        ).getInfo(),

        'aoi_bounds': aoi.bounds().getInfo()
    }


def clip_and_export(
    image,
    aoi,
    description='SLICKTRACE_S1_Bhatkal_20260815'
):
    """
    Clip Sentinel-1 VV/VH to the AOI and start
    an Earth Engine export to Google Drive.
    """

    clipped = (
        image
        .select(['VV', 'VH'])
        .clip(aoi)
    )

    task = ee.batch.Export.image.toDrive(
        image=clipped,
        description=description,
        folder='SLICKTRACE',
        fileNamePrefix='sentinel1_bhatkal_20260815',
        region=aoi,
        scale=10,
        fileFormat='GeoTIFF',
        maxPixels=1e9
    )

    task.start()

    print('Google Drive export started.')
    print('Task ID:', task.id)
    print('Export name: sentinel1_bhatkal_20260815')
    print('Open Google Earth Engine Tasks to monitor progress.')

    return task

    # Make sure the output directory exists
    output_directory = os.path.dirname(out_path)

    if output_directory:
        os.makedirs(
            output_directory,
            exist_ok=True
        )

    print(f'Exporting SAR image to: {out_path}')
    print('Bands: VV, VH')
    print('Resolution: 10 meters')

    geemap.ee_export_image(
        clipped,
        filename=out_path,
        scale=10,
        region=aoi,
        file_per_band=False
    )

    return out_path


if __name__ == '__main__':

    # --------------------------------------------------
    # 1. Define Bhatkal AOI
    # --------------------------------------------------

    aoi = get_aoi(
        lat=13.9,
        lon=74.55,
        buffer_km=25
    )

    # --------------------------------------------------
    # 2. Find Sentinel-1 candidates
    # --------------------------------------------------

    collection = get_sentinel1_collection(
        aoi,
        '2026-08-05',
        '2026-08-25'
    )

    count = collection.size().getInfo()

    print('Images found:', count)

    if count == 0:
        print('No Sentinel-1 images found.')
        exit()

    # --------------------------------------------------
    # 3. Select closest scene to 15 August 2026
    # --------------------------------------------------

    target_date = '2026-08-15'

    best = select_closest_image(
        collection,
        target_date
    )

    selected_id = best.get(
        'system:index'
    ).getInfo()

    selected_date = ee.Date(
        best.get('system:time_start')
    ).format('YYYY-MM-dd').getInfo()

    print('Target date:', target_date)
    print('Selected image ID:', selected_id)
    print('Selected image date:', selected_date)

    # --------------------------------------------------
    # 4. Get metadata
    # --------------------------------------------------

    metadata = get_scene_metadata(
        best,
        aoi
    )

    print('\nScene metadata:')
    print(json.dumps(
        metadata,
        indent=2
    ))

    # --------------------------------------------------
    # 5. Save metadata
    # --------------------------------------------------

    os.makedirs(
        'metadata',
        exist_ok=True
    )

    metadata_path = (
        f'metadata/{selected_id}.json'
    )

    with open(
        metadata_path,
        'w',
        encoding='utf-8'
    ) as file:

        json.dump(
            metadata,
            file,
            indent=2
        )

    print(
        f'\nMetadata saved to: {metadata_path}'
    )

    # --------------------------------------------------
    # 6. Clip and export raw GeoTIFF
    # --------------------------------------------------

    task = clip_and_export(
    best,
    aoi
)

print(
    '\nExport task submitted successfully.'
)