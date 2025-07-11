from vgridpandas import s2pandas  # noqa: F401
import pytest
from shapely.geometry import Polygon, LineString, MultiLineString, box, Point
import pandas as pd
import geopandas as gpd
from geopandas.testing import assert_geodataframe_equal

# TODO: Make sure methods are tested both for
#  DataFrame and GeoDataFrame (where applicable)
# TODO: Test return_geometry functionality

# Fixtures


@pytest.fixture
def basic_dataframe():
    """DataFrame with lat and lng columns"""
    return pd.DataFrame({"lat": [50, 51], "lon": [14, 15]})


@pytest.fixture
def basic_geodataframe(basic_dataframe):
    """GeoDataFrame with POINT geometry"""
    geometry = gpd.points_from_xy(basic_dataframe["lon"], basic_dataframe["lat"])
    return gpd.GeoDataFrame(geometry=geometry, crs="epsg:4326")


@pytest.fixture
def basic_geodataframe_polygon(basic_geodataframe):
    geom = box(0, 0, 1, 1)
    return gpd.GeoDataFrame(geometry=[geom], crs="epsg:4326")


@pytest.fixture
def basic_geodataframe_linestring():
    geom = LineString([(174.793092, -37.005372), (175.621138, -40.323142)])
    return gpd.GeoDataFrame(geometry=[geom], crs="epsg:4326")


@pytest.fixture
# NB one of the LineString parts traverses the antimeridian
def basic_geodataframe_multilinestring(basic_geodataframe):
    geom = MultiLineString(
        [
            [[174.793092, -37.005372], [175.621138, -40.323142]],
            [
                [168.222656, -45.79817],
                [171.914063, -34.307144],
                [178.769531, -37.926868],
                [183.515625, -43.992815],
            ],
        ]
    )
    return gpd.GeoDataFrame(geometry=[geom], crs="epsg:4326")


@pytest.fixture
def basic_geodataframe_empty_linestring():
    """GeoDataFrame with Empty geometry"""
    return gpd.GeoDataFrame(geometry=[LineString()], crs="epsg:4326")


@pytest.fixture
def basic_geodataframe_polygons(basic_geodataframe):
    geoms = [box(0, 0, 1, 1), box(0, 0, 2, 2)]
    return gpd.GeoDataFrame(geometry=geoms, crs="epsg:4326")


@pytest.fixture
def basic_dataframe_with_values(basic_dataframe):
    """DataFrame with lat and lng columns and values"""
    return basic_dataframe.assign(val=[2, 5])


@pytest.fixture
def basic_geodataframe_with_values(basic_geodataframe):
    """GeoDataFrame with POINT geometry and values"""
    return basic_geodataframe.assign(val=[2, 5])


@pytest.fixture
def indexed_dataframe(basic_dataframe):
    """DataFrame with lat, lng and resolution 9 s2 index"""
    return basic_dataframe.assign(
        s2_09=["891e3097383ffff", "891e2659c2fffff"]
    ).set_index("s2_09")


@pytest.fixture
def s2_dataframe_with_values():
    """DataFrame with resolution 9 s2 index and values"""
    index = ["891f1d48177ffff", "891f1d48167ffff", "891f1d4810fffff"]
    return pd.DataFrame({"val": [1, 2, 5]}, index=index)


@pytest.fixture
def s2_geodataframe_with_values(s2_dataframe_with_values):
    """GeoDataFrame with resolution 9 s2 index, values, and Hexagon geometries"""
    geometry = [
        Polygon(cell_to_boundary_lng_lat(h)) for h in s2_dataframe_with_values.index
    ]
    return gpd.GeoDataFrame(
        s2_dataframe_with_values, geometry=geometry, crs="epsg:4326"
    )


@pytest.fixture
def s2_geodataframe_with_polyline_values(basic_geodataframe_linestring):
    return basic_geodataframe_linestring.assign(val=10)


# Tests: s2 API
class TestGeoTos2:
    def test_geo_to_s2(self, basic_dataframe):
        result = basic_dataframe.s2.latlon2s2(9)
        expected = basic_dataframe.assign(
            s2_09=["470bb4", "470924"]
        ).set_index("s2_09")

        pd.testing.assert_frame_equal(expected, result)

    # def test_geo_to_s2_geo(self, basic_geodataframe):
    #     result = basic_geodataframe.s2.latlon2s2(9)
    #     expected = basic_geodataframe.assign(
    #         s2_09=["891e3097383ffff", "891e2659c2fffff"]
    #     ).set_index("s2_09")

    #     pd.testing.assert_frame_equal(expected, result)

    # def test_geo_to_s2_polygon(self, basic_geodataframe_polygon):
    #     with pytest.raises(ValueError):
    #         basic_geodataframe_polygon.s2.latlon2s2(9)


# class Tests2ToGeo:
#     def test_s2_to_geo(self, indexed_dataframe):
#         lats = [50.000551554902586, 51.000121447274736]
#         lngs = [14.000372151097624, 14.999768926738376]
#         geometry = gpd.points_from_xy(x=lngs, y=lats, crs="epsg:4326")
#         expected = gpd.GeoDataFrame(indexed_dataframe, geometry=geometry)
#         result = indexed_dataframe.s2.s22latlon()
#         assert_geodataframe_equal(expected, result, check_less_precise=True)

#     def test_s2_to_geo_boundary(self, indexed_dataframe):
#         h1 = (
#             (13.997875502962215, 50.00126530465277),
#             (13.997981974191347, 49.99956539765703),
#             (14.000478563108897, 49.99885162163456),
#             (14.002868770645003, 49.99983773856239),
#             (14.002762412857178, 50.00153765760209),
#             (14.000265734090084, 50.00225144767143),
#             (13.997875502962215, 50.00126530465277),
#         )
#         h2 = (
#             (14.9972390328545, 51.00084372147122),
#             (14.99732334029277, 50.99916437137475),
#             (14.999853173220332, 50.99844207137708),
#             (15.002298787294139, 50.99939910547163),
#             (15.002214597747209, 51.00107846572982),
#             (14.999684676233445, 51.00180078173323),
#             (14.9972390328545, 51.00084372147122),
#         )
#         geometry = [Polygon(h1), Polygon(h2)]

#         result = indexed_dataframe.s2.s22geo()
#         expected = gpd.GeoDataFrame(
#             indexed_dataframe, geometry=geometry, crs="epsg:4326"
#         )
#         assert_geodataframe_equal(expected, result, check_less_precise=True)


# class Tests2ToGeoBoundary:
#     def test_s2_to_geo_boundary_wrong_index(self, indexed_dataframe):
#         indexed_dataframe.index = [str(indexed_dataframe.index[0])] + ["invalid"]
#         with pytest.raises(ValueError):
#             indexed_dataframe.s2.s22geo()


# class Tests2ToParent:
#     def test_s2_to_parent_level_1(self, s2_dataframe_with_values):
#         s2_parent = "811f3ffffffffff"
#         result = s2_dataframe_with_values.s2.s22parent(1)
#         expected = s2_dataframe_with_values.assign(s2_01=s2_parent)

#         pd.testing.assert_frame_equal(expected, result)

#     def test_s2_to_direct_parent(self, s2_dataframe_with_values):
#         s2_parents = ["881f1d4817fffff", "881f1d4817fffff", "881f1d4811fffff"]
#         result = s2_dataframe_with_values.s2.s22parent()
#         expected = s2_dataframe_with_values.assign(s2_parent=s2_parents)

#         pd.testing.assert_frame_equal(expected, result)

#     def test_s2_to_parent_level_0(self, s2_dataframe_with_values):
#         s2_parent = "801ffffffffffff"
#         result = s2_dataframe_with_values.s2.s22parent(0)
#         expected = s2_dataframe_with_values.assign(s2_00=s2_parent)

#         pd.testing.assert_frame_equal(expected, result)


# class Tests2ToCenterChild:
#     def test_s2_to_center_child(self, indexed_dataframe):
#         expected = indexed_dataframe.assign(
#             s2_center_child=["8a1e30973807fff", "8a1e2659c2c7fff"]
#         )
#         result = indexed_dataframe.s2.s2_to_center_child()
#         pd.testing.assert_frame_equal(expected, result)


# class TestPolyfill:
#     def test_empty_polyfill(self, s2_geodataframe_with_values):
#         expected = s2_geodataframe_with_values.assign(
#             s2_polyfill=[list(), list(), list()]
#         )
#         result = s2_geodataframe_with_values.s2.polyfill(1)
#         assert_geodataframe_equal(expected, result)

#     def test_polyfill(self, s2_geodataframe_with_values):
#         expected_cells = [
#             {
#                 "8a1f1d481747fff",
#                 "8a1f1d48174ffff",
#                 "8a1f1d481757fff",
#                 "8a1f1d48175ffff",
#                 "8a1f1d481767fff",
#                 "8a1f1d48176ffff",
#                 "8a1f1d481777fff",
#             },
#             {
#                 "8a1f1d481647fff",
#                 "8a1f1d48164ffff",
#                 "8a1f1d481657fff",
#                 "8a1f1d48165ffff",
#                 "8a1f1d481667fff",
#                 "8a1f1d48166ffff",
#                 "8a1f1d481677fff",
#             },
#             {
#                 "8a1f1d4810c7fff",
#                 "8a1f1d4810cffff",
#                 "8a1f1d4810d7fff",
#                 "8a1f1d4810dffff",
#                 "8a1f1d4810e7fff",
#                 "8a1f1d4810effff",
#                 "8a1f1d4810f7fff",
#             },
#         ]
#         expected = s2_geodataframe_with_values.assign(s2_polyfill=expected_cells)
#         result = s2_geodataframe_with_values.s2.polyfill(10)
#         result["s2_polyfill"] = result["s2_polyfill"].apply(
#             set
#         )  # Convert to set for testing
#         assert_geodataframe_equal(expected, result)

#     def test_polyfill_explode(self, s2_geodataframe_with_values):
#         expected_indices = set().union(
#             *[
#                 {
#                     "8a1f1d481747fff",
#                     "8a1f1d48174ffff",
#                     "8a1f1d481757fff",
#                     "8a1f1d48175ffff",
#                     "8a1f1d481767fff",
#                     "8a1f1d48176ffff",
#                     "8a1f1d481777fff",
#                 },
#                 {
#                     "8a1f1d481647fff",
#                     "8a1f1d48164ffff",
#                     "8a1f1d481657fff",
#                     "8a1f1d48165ffff",
#                     "8a1f1d481667fff",
#                     "8a1f1d48166ffff",
#                     "8a1f1d481677fff",
#                 },
#                 {
#                     "8a1f1d4810c7fff",
#                     "8a1f1d4810cffff",
#                     "8a1f1d4810d7fff",
#                     "8a1f1d4810dffff",
#                     "8a1f1d4810e7fff",
#                     "8a1f1d4810effff",
#                     "8a1f1d4810f7fff",
#                 },
#             ]
#         )
#         result = s2_geodataframe_with_values.s2.polyfill(10, explode=True)
#         assert len(result) == len(s2_geodataframe_with_values) * 7
#         assert set(result["s2_polyfill"]) == expected_indices
#         assert not result["val"].isna().any()

#     def test_polyfill_explode_unequal_lengths(self, basic_geodataframe_polygons):
#         expected_indices = {
#             "83754efffffffff",
#             "83756afffffffff",
#             "83754efffffffff",
#             "837541fffffffff",
#             "83754cfffffffff",
#         }
#         result = basic_geodataframe_polygons.s2.polyfill(3, explode=True)
#         assert len(result) == 5
#         assert set(result["s2_polyfill"]) == expected_indices


# class TestCellArea:
#     def test_cell_area(self, indexed_dataframe):
#         expected = indexed_dataframe.assign(
#             s2_cell_area=[0.09937867173389912, 0.09775508251476996]
#         )
#         result = indexed_dataframe.s2.cell_area()
#         pd.testing.assert_frame_equal(expected, result)


# class Tests2GetResolution:
#     def test_s2_get_resolution(self, s2_dataframe_with_values):
#         expected = s2_dataframe_with_values.assign(s2_resolution=9)
#         result = s2_dataframe_with_values.s2.s2_get_resolution()
#         pd.testing.assert_frame_equal(expected, result)

#     def test_s2_get_resolution_index_only(self, s2_dataframe_with_values):
#         del s2_dataframe_with_values["val"]
#         expected = s2_dataframe_with_values.assign(s2_resolution=9)
#         result = s2_dataframe_with_values.s2.s2_get_resolution()
#         pd.testing.assert_frame_equal(expected, result)


# class Tests2GetBaseCell:
#     def test_s2_get_base_cell(self, indexed_dataframe):
#         expected = indexed_dataframe.assign(s2_base_cell=[15, 15])
#         result = indexed_dataframe.s2.s2_get_base_cell()
#         pd.testing.assert_frame_equal(expected, result)


# class Tests2IsValid:
#     def test_s2_is_valid(self, indexed_dataframe):
#         indexed_dataframe.index = [str(indexed_dataframe.index[0])] + ["invalid"]
#         expected = indexed_dataframe.assign(s2_is_valid=[True, False])
#         result = indexed_dataframe.s2.s2_is_valid()
#         pd.testing.assert_frame_equal(expected, result)