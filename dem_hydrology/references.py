# -*- coding: utf-8 -*-
"""Daftar pustaka yang menjadi dasar setiap analisis (dipakai UI, Excel, dan PDF)."""

REFS = {
    "barnes2014": "Barnes, R., Lehman, C., Mulla, D. (2014). Priority-flood: an optimal depression-filling and "
                  "watershed-labeling algorithm for digital elevation models. Computers & Geosciences 62, 117-127.",
    "wang2006": "Wang, L., Liu, H. (2006). An efficient method for identifying and filling surface depressions in "
                "digital elevation models for hydrologic analysis and modelling. Int. J. Geographical Information "
                "Science 20(2), 193-213.",
    "garbrecht1997": "Garbrecht, J., Martz, L.W. (1997). The assignment of drainage direction over flat surfaces in "
                     "raster digital elevation models. Journal of Hydrology 193, 204-213.",
    "horn1981": "Horn, B.K.P. (1981). Hill shading and the reflectance map. Proceedings of the IEEE 69(1), 14-47.",
    "zevenbergen1987": "Zevenbergen, L.W., Thorne, C.R. (1987). Quantitative analysis of land surface topography. "
                       "Earth Surface Processes and Landforms 12, 47-56.",
    "weiss2001": "Weiss, A.D. (2001). Topographic Position and Landforms Analysis. Poster, ESRI International "
                 "User Conference, San Diego.",
    "riley1999": "Riley, S.J., DeGloria, S.D., Elliot, R. (1999). A terrain ruggedness index that quantifies "
                 "topographic heterogeneity. Intermountain Journal of Sciences 5(1-4), 23-27.",
    "mentan1980": "Keputusan Menteri Pertanian No. 837/Kpts/Um/11/1980 tentang Kriteria dan Tata Cara Penetapan "
                  "Hutan Lindung (kelas lereng I-V: 0-8, 8-15, 15-25, 25-45, >45 %).",
    "ocallaghan1984": "O'Callaghan, J.F., Mark, D.M. (1984). The extraction of drainage networks from digital "
                      "elevation data. Computer Vision, Graphics, and Image Processing 28(3), 323-344.",
    "jenson1988": "Jenson, S.K., Domingue, J.O. (1988). Extracting topographic structure from digital elevation data "
                  "for geographic information system analysis. Photogrammetric Engineering and Remote Sensing "
                  "54(11), 1593-1600.",
    "tarboton1997": "Tarboton, D.G. (1997). A new method for the determination of flow directions and upslope areas "
                    "in grid digital elevation models. Water Resources Research 33(2), 309-319.",
    "quinn1991": "Quinn, P., Beven, K., Chevallier, P., Planchon, O. (1991). The prediction of hillslope flow paths "
                 "for distributed hydrological modelling using digital terrain models. Hydrological Processes "
                 "5(1), 59-79.",
    "freeman1991": "Freeman, T.G. (1991). Calculating catchment area with divergent flow based on a regular grid. "
                   "Computers & Geosciences 17(3), 413-422.",
    "montgomery1992": "Montgomery, D.R., Dietrich, W.E. (1992). Channel initiation and the problem of landscape "
                      "scale. Science 255, 826-830.",
    "strahler1957": "Strahler, A.N. (1957). Quantitative analysis of watershed geomorphology. Transactions, "
                    "American Geophysical Union 38(6), 913-920.",
    "shreve1966": "Shreve, R.L. (1966). Statistical law of stream numbers. Journal of Geology 74(1), 17-37.",
    "horton1932": "Horton, R.E. (1932). Drainage-basin characteristics. Transactions, American Geophysical Union "
                  "13, 350-361.",
    "horton1945": "Horton, R.E. (1945). Erosional development of streams and their drainage basins: hydrophysical "
                  "approach to quantitative morphology. GSA Bulletin 56(3), 275-370.",
    "schumm1956": "Schumm, S.A. (1956). Evolution of drainage systems and slopes in badlands at Perth Amboy, New "
                  "Jersey. GSA Bulletin 67(5), 597-646.",
    "miller1953": "Miller, V.C. (1953). A quantitative geomorphic study of drainage basin characteristics in the "
                  "Clinch Mountain area, Virginia and Tennessee. Columbia University, Technical Report 3.",
    "gravelius1914": "Gravelius, H. (1914). Grundriss der gesamten Gewaesserkunde, Band 1: Flusskunde. Goeschen, "
                     "Berlin.",
    "melton1957": "Melton, M.A. (1957). An analysis of the relations among elements of climate, surface properties "
                  "and geomorphology. Columbia University, Technical Report 11.",
    "strahler1952": "Strahler, A.N. (1952). Hypsometric (area-altitude) analysis of erosional topography. GSA "
                    "Bulletin 63(11), 1117-1142.",
    "pike1971": "Pike, R.J., Wilson, S.E. (1971). Elevation-relief ratio, hypsometric integral, and geomorphic "
                "area-altitude analysis. GSA Bulletin 82, 1079-1084.",
    "smith1950": "Smith, K.G. (1950). Standards for grading texture of erosional topography. American Journal of "
                 "Science 248, 655-668.",
    "faniran1968": "Faniran, A. (1968). The index of drainage intensity - a provisional new drainage factor. "
                   "Australian Journal of Science 31, 328-330.",
    "kirpich1940": "Kirpich, Z.P. (1940). Time of concentration of small agricultural watersheds. Civil "
                   "Engineering 10(6), 362.",
    "giandotti1934": "Giandotti, M. (1934). Previsione delle piene e delle magre dei corsi d'acqua. Memorie e "
                     "Studi Idrografici 8, Istituto Poligrafico dello Stato, Roma.",
    "taylor1952": "Taylor, A.B., Schwarz, H.E. (1952). Unit-hydrograph lag and peak flow related to basin "
                  "characteristics. Transactions, American Geophysical Union 33(2), 235-246.",
    "beven1979": "Beven, K.J., Kirkby, M.J. (1979). A physically based, variable contributing area model of basin "
                 "hydrology. Hydrological Sciences Bulletin 24(1), 43-69.",
    "sorensen2006": "Sorensen, R., Zinko, U., Seibert, J. (2006). On the calculation of the topographic wetness "
                    "index: evaluation of different methods based on field observations. Hydrology and Earth "
                    "System Sciences 10, 101-112.",
    "moore1991": "Moore, I.D., Grayson, R.B., Ladson, A.R. (1991). Digital terrain modelling: a review of "
                 "hydrological, geomorphological, and biological applications. Hydrological Processes 5(1), 3-30.",
    "moore1986": "Moore, I.D., Burch, G.J. (1986). Physical basis of the length-slope factor in the Universal Soil "
                 "Loss Equation. Soil Science Society of America Journal 50, 1294-1298.",
    "desmet1996": "Desmet, P.J.J., Govers, G. (1996). A GIS procedure for automatically calculating the USLE LS "
                  "factor on topographically complex landscape units. Journal of Soil and Water Conservation "
                  "51(5), 427-433.",
    "mccool1987": "McCool, D.K., Brown, L.C., Foster, G.R., Mutchler, C.K., Meyer, L.D. (1987). Revised slope "
                  "steepness factor for the Universal Soil Loss Equation. Transactions of the ASAE 30(5), "
                  "1387-1396.",
    "mccool1989": "McCool, D.K., Foster, G.R., Mutchler, C.K., Meyer, L.D. (1989). Revised slope length factor for "
                  "the Universal Soil Loss Equation. Transactions of the ASAE 32(5), 1571-1576.",
    "nearing1997": "Nearing, M.A. (1997). A single, continuous function for slope steepness influence on soil "
                   "loss. Soil Science Society of America Journal 61(3), 917-919.",
    "renard1997": "Renard, K.G., Foster, G.R., Weesies, G.A., McCool, D.K., Yoder, D.C. (1997). Predicting Soil "
                  "Erosion by Water: A Guide to Conservation Planning with the Revised Universal Soil Loss "
                  "Equation (RUSLE). USDA Agriculture Handbook 703.",
    "renno2008": "Renno, C.D., Nobre, A.D., Cuartas, L.A., Soares, J.V., Hodnett, M.G., Tomasella, J., Waterloo, "
                 "M.J. (2008). HAND, a new terrain descriptor using SRTM-DEM: mapping terra-firme rainforest "
                 "environments in Amazonia. Remote Sensing of Environment 112, 3469-3481.",
    "nobre2011": "Nobre, A.D., Cuartas, L.A., Hodnett, M., Renno, C.D., Rodrigues, G., Silveira, A., Waterloo, M., "
                 "Saleska, S. (2011). Height Above the Nearest Drainage - a hydrologically relevant new terrain "
                 "model. Journal of Hydrology 404, 13-29.",
    "nobre2016": "Nobre, A.D., Cuartas, L.A., Momo, M.R., Severo, D.L., Pinheiro, A., Nobre, C.A. (2016). HAND "
                 "contour: a new proxy predictor of inundation extent. Hydrological Processes 30, 320-333.",
    "poulter2008": "Poulter, B., Halpin, P.N. (2008). Raster modelling of coastal flooding from sea-level rise. "
                   "International Journal of Geographical Information Science 22(2), 167-182.",
    "nrcs1986": "USDA-NRCS (1986). Urban Hydrology for Small Watersheds, Technical Release 55 (TR-55).",
    "manning1891": "Manning, R. (1891). On the flow of water in open channels and pipes. Transactions of the "
                   "Institution of Civil Engineers of Ireland 20, 161-207.",
    "maidment1993": "Maidment, D.R. (1993). GIS and hydrologic modeling. In: Goodchild, Parks, Steyaert (eds.), "
                    "Environmental Modeling with GIS. Oxford University Press, 147-167.",
    "manfreda2011": "Manfreda, S., Di Leo, M., Sole, A. (2011). Detection of flood-prone areas using digital "
                    "elevation models. Journal of Hydrologic Engineering 16(10), 781-790.",
    "samela2017": "Samela, C., Troy, T.J., Manfreda, S. (2017). Geomorphic classifiers for flood-prone areas "
                  "delineation for data-scarce environments. Advances in Water Resources 102, 13-28.",
    "magesh2012": "Magesh, N.S., Chandrasekar, N., Soundranayagam, J.P. (2012). Delineation of groundwater "
                  "potential zones in Theni district, Tamil Nadu, using remote sensing, GIS and MIF techniques. "
                  "Geoscience Frontiers 3(2), 189-196.",
    "rahmati2015": "Rahmati, O., Nazari Samani, A., Mahdavi, M., Pourghasemi, H.R., Zeinivand, H. (2015). "
                   "Groundwater potential mapping at Kurdistan region of Iran using analytic hierarchy process "
                   "and GIS. Arabian Journal of Geosciences 8, 7059-7071.",
}
