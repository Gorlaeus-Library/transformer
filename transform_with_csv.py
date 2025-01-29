import copy

from saxonche import *
import os
import xml.etree.ElementTree as ET
import pandas as pd

mods_xslt = "MODS3-7_MARC21slim_XSLT2-0.xsl"
input_dir = "alles_in_1"
output_dir = "translations"
csv = "export.csv"

# read in the csv data
inventory = pd.read_csv(csv, sep=';')
#inventory = inventory.astype(str)
print(inventory.head())
print(inventory.columns)

ET.register_namespace('marc', 'http://www.loc.gov/MARC21/slim')

# this little script is there to protect against an error from the embargo field
def is_float(string):
    try:
        float(string)
        return True
    except ValueError:
        return False

# iterate through parents
# selection is based upon them not having a parentid
inventory_parents = inventory[(inventory["parent_id"].isnull())]
for index, row in inventory_parents.iterrows():
    # create a new xml for the collection
    collection_xml = ET.parse("collection_base.xml")
    collection_root = collection_xml.getroot()
    print(collection_root)


    # open the mods xml from our parents
    parent_mods_tree = ET.parse(os.path.join(input_dir, row['mods_file_name']))
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
        group_id = ET.Element("controlfield")
        group_id.set("tag", "001")
        group_id.text = str(row['item_id'])
        parent_marc.append(group_id)

        # add a field 001 with the item_number

        collection_root.append(parent_marc)

        # get the files
        #from our dataframe
        inventory_children = inventory[(inventory["parent_id"]==row["item_id"])]
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
            file_block = ET.Element("datafield")
            file_block.set("tag", "856")
            file_block.set("ind1", "4")
            file_block.set("ind2", " ")

            # label
            counter_text = ""
            if file_counter < 10:
                counter_text = "0"
            counter_text = counter_text + str(file_counter) + ". "
            file_block_label = ET.Element("subfield")
            file_block_label.set("code", "a")
            file_block_label.text = counter_text + child_row['child_title']
            file_block.append(file_block_label)

            # filename
            file_block_filename = ET.Element("subfield")
            file_block_filename.set("code", "u")
            file_block_filename.text = child_row['obj_file_name']
            file_block.append(file_block_filename)

            # access rights
            file_block_access = ET.Element("subfield")
            file_block_access.set("code", "l")
            file_block_access.text = child_row['access_code']
            file_block.append(file_block_access)

            # embargo
            if (not is_float(child_row['embargo_date'])):
                file_block_embargo = ET.Element("subfield")
                file_block_embargo.set("code", "z")
                file_block_embargo.text = "embargo:" + str(child_row['embargo_date'])
                file_block.append(file_block_embargo)

            # use and reproduction
            file_block_use = ET.Element("subfield")
            file_block_use.set("code", "r")
            file_block_use.text = child_row['access_use']
            file_block.append(file_block_use)

            # version
            if (child_row[ 'version'] is not None):
                file_block_version = ET.Element("subfield")
                file_block_version.set("code", "z")
                file_block_version.text = "version:" + child_row['version']
                file_block.append(file_block_version)

            # doi
            if (child_row['identifier_doi'] is not None):
                file_block_doi = ET.Element("subfield")
                file_block_doi.set("code", "g")
                file_block_doi.text = child_row['identifier_doi']
               # file_block.append(file_block_doi)

            # converis file id
            if (child_row['identifier_local'] is not None):
                file_block_fileid = ET.Element("subfield")
                file_block_fileid.set("code", "g")
                file_block_fileid.text = child_row['identifier_local']
                file_block.append(file_block_fileid)

            #add the fileblock to our child
            child_root.append(file_block)




            # add child to collection
            collection_root.append(child_root)

        # now save the output
        filename_output = "marc_col_" + str(row['item_id']) + ".xml"
        collection_xml.write(os.path.join(output_dir, filename_output), encoding='utf8')


