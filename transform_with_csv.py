import copy

from saxonche import *
import os
import os.path
import subprocess
import xml.etree.ElementTree as ET
import pandas as pd

mods_xslt = "MODS3-7_MARC21slim_XSLT2-0.xsl"
input_dir = "alles_in_1"
output_dir = "translations"
csv = "export_lucas.csv"

# read in the csv data
inventory = pd.read_csv(csv, sep=';', dtype=str) #geforceerd als string inlezen
#inventory = inventory.astype(str)
print(inventory.head())
print(inventory.columns)

ET.register_namespace('marc', 'http://www.loc.gov/MARC21/slim')

# this little script is there to protect against an error from the embargo field
def is_float(string):
    try:
        float(string)
        return True
    except:
        return False


# retrieve a file from the fedora server and copy it to a target file
def retrieve_file_from_fedora_server(source_file, target_file):
    if not os.path.isfile(target_file):
        subprocess.run(["scp", "-p", "-q", "-J", "adminschaiklbvan@zandvlo", "adminschaiklbvan@isp2:/var/datastreams/" + source_file, target_file])

# return the file extension based on mimetype
def get_extension_for_mimetype(mimetype):
    mime2ext = {
      "image/tiff": "tif",
      "image/jp2": "jp2",
      "application/xml": "xml",
      "audio/vnd.wave": "wav",
      "application/pdf": "pdf",
      "image/jpg": "jpg"
    }
    return mime2ext.get(mimetype, 'unknown')

# iterate through parents
# selection is based upon them not having a parentid
inventory_parents = inventory[(inventory["parent_id"].isnull())]
for index, row in inventory_parents.iterrows():
    # create a new xml for the collection
    collection_xml = ET.parse("collection_base.xml")
    collection_root = collection_xml.getroot()
    print(collection_root)

    # retrieve mods file if needed
    mods_filename = os.path.join(input_dir, str(row['item_id']).replace(':', '_') + '_MODS.xml')
    retrieve_file_from_fedora_server(row['mods_fedora_filepath'], mods_filename)

    # open the mods xml from our parents
    parent_mods_tree = ET.parse(mods_filename)
    parent_mods_root = parent_mods_tree.getroot()

    # translate the basic mods to marc21
    with PySaxonProcessor(license=False) as proc:
        print(proc.version)
        xsltproc = proc.new_xslt30_processor()
        document = proc.parse_xml(
            xml_text=ET.tostring(parent_mods_root, encoding="unicode"))
        executable = xsltproc.compile_stylesheet(stylesheet_file=mods_xslt)
        output = executable.transform_to_string(xdm_node=document)

        # add the new marc record to our collection
        parent_marc = ET.fromstring(output)

        #create a field 001 to connect the records
        group_id = ET.Element("marc:controlfield")
        group_id.set("tag", "001")
        group_id.text = str(row['item_id'])
        parent_marc.append(group_id)

        # add a field 001 with the item_number

        collection_root.append(parent_marc)

        # get the files
        #from our dataframe
        parent_id = 'info:fedora/' + row["item_id"]
        inventory_children = inventory[(inventory["parent_id"] == parent_id)]
        file_counter = 1
        for child_index, child_row in inventory_children.iterrows():
            print(child_row)

            # let's start by making a record
            child_xml = ET.parse("record_base.xml")
            child_root = child_xml.getroot()

            # copy some basic fields from the parent to the child
            lead = parent_marc.find(".//{http://www.loc.gov/MARC21/slim}leader") #{http://www.loc.gov/MARC21/slim}
            child_lead = copy.deepcopy(lead)
            child_root.append(child_lead)

            child_group_id = copy.deepcopy(group_id)
            child_root.append(child_group_id)

            field_eight = parent_marc.find(".//{http://www.loc.gov/MARC21/slim}controlfield")
            child_eight = copy.deepcopy(field_eight)
            child_root.append(child_eight)

            title = parent_marc.find(".//{http://www.loc.gov/MARC21/slim}datafield[@tag='245']")
            child_title = copy.deepcopy(title)
            child_root.append(child_title)

            # create a fileblock
            file_block = ET.Element("marc:datafield")
            file_block.set("tag", "856")
            file_block.set("ind1", "4")
            file_block.set("ind2", " ")

            # label
            file_block_label = ET.Element("marc:subfield")
            file_block_label.set("code", "a")
            file_block_label.text = "{:02d}. {!s}".format(file_counter, child_row['title'])
            file_block.append(file_block_label)

            # retrieve obj file if needed
            extension = get_extension_for_mimetype(child_row['obj_mimetype'])
            obj_filename = str(child_row['item_id']).replace(':', '_') + '_OBJ.' + extension
            retrieve_file_from_fedora_server(str(child_row['obj_fedora_filepath']), obj_filename)

            # filename
            file_block_filename = ET.Element("marc:subfield")
            file_block_filename.set("code", "u")
            file_block_filename.text = obj_filename
            file_block.append(file_block_filename)

            # access rights
            file_block_access = ET.Element("marc:subfield")
            file_block_access.set("code", "l")
            file_block_access.text = str(child_row['access_code'])
            file_block.append(file_block_access)

            # embargo
            if (not is_float(child_row['embargo_date'])):
                file_block_embargo = ET.Element("marc:subfield")
                file_block_embargo.set("code", "z")
                file_block_embargo.text = "embargo:" + str(child_row['embargo_date'])
                file_block.append(file_block_embargo)

            # use and reproduction
            file_block_use = ET.Element("marc:subfield")
            file_block_use.set("code", "r")
            file_block_use.text = child_row['access_use']
            file_block.append(file_block_use)

            # version
            if (child_row[ 'version'] is not None):
                file_block_version = ET.Element("marc:subfield")
                file_block_version.set("code", "z")
                file_block_version.text = "version:" + child_row['version']
                file_block.append(file_block_version)

            # doi
            if (child_row['identifier_doi'] is not None):
                file_block_doi = ET.Element("marc:subfield")
                file_block_doi.set("code", "g")
                file_block_doi.text = str(child_row['identifier_doi'])
               # file_block.append(file_block_doi)

            # converis file id
            if (child_row['identifier_local'] is not None):
                file_block_fileid = ET.Element("marc:subfield")
                file_block_fileid.set("code", "g")
                file_block_fileid.text = child_row['identifier_local']
                file_block.append(file_block_fileid)

            #add the fileblock to our child
            child_root.append(file_block)




            # add child to collection
            collection_root.append(child_root)
            file_counter = file_counter + 1

        # now save the output
        filename_output = "marc_col_" + str(row['item_id']).replace(':', '_') + ".xml"

        collection_xml.write(os.path.join(output_dir, filename_output), encoding='UTF-8')


