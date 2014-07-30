# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# merge_layers.py
# Created on: 2014-05-21 09:48:06.00000
#   (generated by ArcGIS/ModelBuilder)
# Description: 
# ---------------------------------------------------------------------------

# Import arcpy module
import arcpy
import os
import archiver
import glob
import sys
import traceback

from config import settings


def import_module(name):
    mod = __import__(name)
    components = name.split('.')
    for comp in components[1:]:
        mod = getattr(mod, comp)
    return mod


def create_field_map(input_name, layer, field):
    fm = arcpy.FieldMap()
    fm.addInputField(input_name, layer['fields'][field][1])
    output_field = fm.outputField
    output_field.name = field
    fm.outputField = output_field

    return fm


def empty_strings2null(fclass):
    desc = arcpy.Describe(fclass)
    if desc.dataType == 'FeatureClass':
        string_fields = [f.name for f in arcpy.ListFields(fclass, None, 'String')]
        for string_field in string_fields:
            arcpy.MakeFeatureLayer_management(fclass,
                                              "update_layer",
                                              '"%s" = \'\'' % string_field,
                                              "",
                                              "")
            arcpy.CalculateField_management("update_layer", string_field, "None", "PYTHON", "")


def merge(mlayer):
    # import layer file given in system argument
    global input_fc

    try:
        import_layers = import_module('layers.' + mlayer)
    except ImportError:
        return "Warning: Layer %s is not defined" % mlayer

    # get layer settings
    target_ws = settings.get_target_gdb()
    target_fc_name = mlayer
    scratch_folder = settings.get_scratch_folder()
    s3_bucket = settings.get_download_bucket()
    bucket_drives = settings.get_bucket_drive()

    layers = import_layers.layers()

    #define name for target feature class and target feature layer
    target_fc = os.path.join(target_ws, target_fc_name)
    target_layer = '%s_layer' % target_fc_name

    # set environment parameters
    arcpy.env.overwriteOutput = True
    arcpy.env.outputCoordinateSystem = arcpy.SpatialReference("WGS 1984 Web Mercator (auxiliary sphere)")

    # Deletes all features in target feature class
    arcpy.DeleteFeatures_management(target_fc)

    # Compact target file-geodatabase to avoid running out of ObjectIDs
    arcpy.Compact_management(target_ws)

    #Add features, one layer at a time
    for layer in layers:

        #try:

        # # update source dataset
        #     try:
        #         if layer['update']['replication']:
        #             #print "update source file" + layer['input_fc_name']
        #             gdb1 = layer['update']['replication'][0]
        #             replica = layer['update']['replication'][1]
        #             gdb2 = layer['update']['replication'][2]
        #
        #             default_trans = arcpy.env.geographicTransformations
        #             defautl_outCoorSys = arcpy.env.outputCoordinateSystem
        #             if len(layer['update']['replication']) >= 3:
        #                 arcpy.env.geographicTransformations = layer['update']['replication'][3]
        #             if len(layer['update']['replication']) >= 4:
        #                 arcpy.env.outputCoordinateSystem = arcpy.SpatialReference(layer['update']['replication'][4])
        #
        #             arcpy.SynchronizeChanges_management(gdb1, replica, gdb2, "FROM_GEODATABASE1_TO_2", "IN_FAVOR_OF_GDB1", "BY_OBJECT", "DO_NOT_RECONCILE")
        #
        #             arcpy.env.geographicTransformations = default_trans
        #             arcpy.env.outputCoordinateSystem = defautl_outCoorSys
        #
        #     except KeyError:
        #         try:
        #             if layer['update']['routine']:
        #                 cmod = import_module('layers.' + layer['update']['routine'])
        #                 print cmod.execute()
        #
        #         except KeyError:
        #             pass

        print "Adding " + layer['input_fc_name']

        # define transformation
        if layer['transformation']:
            arcpy.env.geographicTransformations = layer['transformation']

        # create feature layer from feature class

        if layer['location'].lower() == 'server':
            input_fc = os.path.join(layer['input_ws'], layer['input_ds'], layer['input_fc_name'])
        elif layer['location'] == 's3':
            input_fc = os.path.join(layer['bucket'][bucket_drives], layer['input_ws'], layer['input_ds'],
                                    layer['input_fc_name'])

        input_layer = os.path.basename('%s_layer') % input_fc

        arcpy.MakeFeatureLayer_management(input_fc,
                                          input_layer,
                                          layer['where_clause'],
                                          "",
                                          "")

        # map fields
        fms = arcpy.FieldMappings()

        for field in layer['fields']:
            if layer['fields'][field]:
                if layer['fields'][field][0] == 'field':
                    fms.addFieldMap(create_field_map(input_layer, layer, field))

        # append layer to target feature class
        arcpy.Append_management(input_layer,
                                target_fc,
                                "NO_TEST",
                                fms,
                                "")

        # Update field values, for un-mapped fields

        arcpy.MakeFeatureLayer_management(target_fc,
                                          target_layer,
                                          "country IS NULL OR country = '%s'" % layer['fields']['country'][1],
                                          "",
                                          "")
        for field in layer['fields']:
            if layer['fields'][field]:

                if layer['fields'][field][0] == 'value':
                    arcpy.CalculateField_management(target_layer, field, "'%s'" % layer['fields'][field][1], "PYTHON", "")

                elif layer['fields'][field][0] == 'expression':
                    arcpy.CalculateField_management(target_layer, field, "%s" % layer['fields'][field][1], "PYTHON", "")

        #convert empty strings ('') to NULL
        empty_strings2null(input_fc)

        # reset transformation
        arcpy.env.geographicTransformations = ""

        #except:
        #   print "Failed to add " + layer['input_fc_name']
        #  traceback.print_exc()


    # Export FeatureClass to Shapefile
    arcpy.FeatureClassToShapefile_conversion([target_fc], scratch_folder)

    # zip shapefile and push to Amazon S3 using archiver.py script
    target_shp = os.path.join(scratch_folder, "%s.shp" % target_fc_name)
    target_zip = os.path.join(scratch_folder, "%s.zip" % target_fc_name)
    #s3_zip = os.path.join("data", "%s.zip" % target_fc_name)
    s3_zip = "%s.zip" % target_fc_name

    archiver.main(target_shp, target_zip, s3_zip, s3_bucket)

    # clean up, delete shapefiles and zipfile
    targets_rm = os.path.join(scratch_folder, "%s.*" % target_fc_name)
    r = glob.glob(targets_rm)
    for i in r:
        os.remove(i)


