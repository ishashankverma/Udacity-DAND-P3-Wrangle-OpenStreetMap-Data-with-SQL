# -*- coding: utf-8 -*-

import xml.etree.cElementTree as ET
from collections import defaultdict
import re
import pprint
import csv
import codecs
import cerberus
import schema
import sqlite3
import string

# Pune India OSM file
osm_file = "pune_india.osm"

# Regular Expression Function
street_type_re = re.compile(r'\b\S+\.?$', re.IGNORECASE)

# Expected street types/names list
expected = ["Street", "Avenue", "Boulevard", "Drive", "Court", "Place",
            "Square", "Lane", "Road", "Trail", "Parkway", "Commons", "Alley",
            "Bridge", "Highway", "Circle", "Terrace", "Way", "Chowk", "Colony", "Marg", "Path"]

# Function to add street names to dictionary by type
def audit_street_type(street_types, street_name):
    m = street_type_re.search(street_name)
    if m:
        street_type = m.group()
        if street_type not in expected:
            street_types[street_type].add(street_name)

# Function to check tags for street data
def is_street_name(elem):
    return (elem.attrib['k'] == "addr:street")

#Function to audit the data for different abbreviations of street types
def audit(osmfile):
    osm_file = open(osmfile, "r")    
    street_types = defaultdict(set)
    for event, elem in ET.iterparse(osm_file, events=("start",)):
        if elem.tag == "node" or elem.tag == "way":
            for tag in elem.iter("tag"):
                if is_street_name(tag):
                    audit_street_type(street_types, tag.attrib['v'])
    osm_file.close()
    return street_types
    
    
# Auditing our osm file
st_types = audit(osm_file)

# Printing results 
pprint.pprint(dict(st_types))

#Mapping the corrections
mapping = { "Rd": "Road",
            "raod": "Road",
            "road": "Road",
           }
            
#New osm file
osm_file_2 = "pune_india_cleaned.osm"

# Function to replace abbreviation by full name in string
def update_name(name, mapping):
    words = name.split(' ')
    last_word = words[-1]
    if last_word in mapping.keys():
        name2 = name.replace(last_word, mapping[last_word])
        return name2
    return name

# Supporting function to get element from osm file
# Takes as input osm file and tuple of nodes and yield nodes of types from tuple. 
def get_element(osm_file, tags=('node', 'way', 'relation')):
    context = iter(ET.iterparse(osm_file, events=('start', 'end')))
    _, root = next(context)
    for event, elem in context:
        if event == 'end' and elem.tag in tags:
            yield elem
            root.clear()
            
# Function to replace abbreviations in osm file
# Saves the output in a new osm file
def modify_street(old_file, new_file):
    with open(new_file, 'wb') as output:
        output.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        output.write('<osm>\n  ') 
        for i, element in enumerate(get_element(old_file)):
            for tag in element.iter("tag"):
                if is_street_name(tag):
                    tag.set('v',update_name(tag.attrib['v'], mapping))
            output.write(ET.tostring(element, encoding='utf-8'))
        output.write('</osm>')

# Modifying osm file
modify_street(osm_file, osm_file_2)

# Checking tag for postcode content 
zip_type_re = re.compile(r'\d{6}-??')

# Sorting zipcodes in different forms and save them to dict
def audit_zip_type(zip_types, zip):
    m = zip_type_re.search(zip)
    if m:
        zip_type = m.group()
        if zip_type not in zip_types:
            zip_types[zip_type].add(zip)
    else:
        zip_types['unknown'].add(zip)

# Checking if tag contains postcode
def is_zip(elem):
    return (elem.attrib['k'] == "addr:postcode")

# Auditing file for different variations of same zip 
def zip_audit(osmfile):
    osm_file = open(osmfile, "r")    
    zip_types = defaultdict(set)
    for event, elem in ET.iterparse(osm_file, events=("start",)):
        if elem.tag == "node" or elem.tag == "way":
            for tag in elem.iter("tag"):
                if is_zip(tag):
                    audit_zip_type(zip_types, tag.attrib['v'])                
    osm_file.close()
    return zip_types
    
# Auditing our osm file
zp_types = zip_audit(osm_file_2)

# Printing results 
pprint.pprint(dict(zp_types))

#New osm file
osm_file_3 = "pune_india_cleaned_2.osm"

# Function to replace abbreviation in zip
def update_zip(zip):
    m = zip_type_re.search(zip)
    if m:
        return m.group()
    else:
        return 'unknown'

# This function corrects the zip in osm file
def modify_zip(old_file, new_file):
    with open(new_file, 'wb') as output:
        output.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        output.write('<osm>\n  ') 
        for i, element in enumerate(get_element(old_file)):
            for tag in element.iter("tag"):
                if is_zip(tag):
                    str(tag).replace(" ", "")
                    tag.set('v',update_zip(tag.attrib['v']))
            output.write(ET.tostring(element, encoding='utf-8'))
        output.write('</osm>')

# Modifying osm file
modify_zip(osm_file_2, osm_file_3)

#Preparing for Database - SQL

# Path to new csv files
NODES_PATH = "nodes.csv"
NODE_TAGS_PATH = "nodes_tags.csv"
WAYS_PATH = "ways.csv"
WAY_NODES_PATH = "ways_nodes.csv"
WAY_TAGS_PATH = "ways_tags.csv"

# Regular expression compilers
LOWER_COLON = re.compile(r'^([a-z]|_)+:([a-z]|_)+')
PROBLEMCHARS = re.compile(r'[=\+/&<>;\'"\?%#$@\,\. \t\r\n]')

# Importing schema for pransformation from schema.py file
SCHEMA = schema.schema

# Fields of new csv files
# Make sure the fields order in the csvs matches the column order in the 
# sql table schema
NODE_FIELDS = ['id', 'lat', 'lon', 'user', 'uid', 'version', 'changeset', 'timestamp']
NODE_TAGS_FIELDS = ['id', 'key', 'value', 'type']
WAY_FIELDS = ['id', 'user', 'uid', 'version', 'changeset', 'timestamp']
WAY_TAGS_FIELDS = ['id', 'key', 'value', 'type']
WAY_NODES_FIELDS = ['id', 'node_id', 'position']


# Main function for transformation of XML data to Python dict
def shape_element(element, node_attr_fields=NODE_FIELDS, way_attr_fields=WAY_FIELDS,
                  problem_chars=PROBLEMCHARS, default_tag_type='regular'):
    """Clean and shape node or way XML element to Python dict"""

    node_attribs = {}
    way_attribs = {}
    way_nodes = []
    tags = []  

    if element.tag == 'node':
        for attrib in element.attrib:
            if attrib in NODE_FIELDS:
                node_attribs[attrib] = element.attrib[attrib]
        
        for child in element:
            node_tag = {}
            if LOWER_COLON.match(child.attrib['k']):
                node_tag['type'] = child.attrib['k'].split(':',1)[0]
                node_tag['key'] = child.attrib['k'].split(':',1)[1]
                node_tag['id'] = element.attrib['id']
                node_tag['value'] = child.attrib['v']
                tags.append(node_tag)
            elif PROBLEMCHARS.match(child.attrib['k']):
                continue
            else:
                node_tag['type'] = 'regular'
                node_tag['key'] = child.attrib['k']
                node_tag['id'] = element.attrib['id']
                node_tag['value'] = child.attrib['v']
                tags.append(node_tag)
        
        return {'node': node_attribs, 'node_tags': tags}
        
    elif element.tag == 'way':
        for attrib in element.attrib:
            if attrib in WAY_FIELDS:
                way_attribs[attrib] = element.attrib[attrib]
        
        position = 0
        for child in element:
            way_tag = {}
            way_node = {}
            
            if child.tag == 'tag':
                if LOWER_COLON.match(child.attrib['k']):
                    way_tag['type'] = child.attrib['k'].split(':',1)[0]
                    way_tag['key'] = child.attrib['k'].split(':',1)[1]
                    way_tag['id'] = element.attrib['id']
                    way_tag['value'] = child.attrib['v']
                    tags.append(way_tag)
                elif PROBLEMCHARS.match(child.attrib['k']):
                    continue
                else:
                    way_tag['type'] = 'regular'
                    way_tag['key'] = child.attrib['k']
                    way_tag['id'] = element.attrib['id']
                    way_tag['value'] = child.attrib['v']
                    tags.append(way_tag)
                    
            elif child.tag == 'nd':
                way_node['id'] = element.attrib['id']
                way_node['node_id'] = child.attrib['ref']
                way_node['position'] = position
                position += 1
                way_nodes.append(way_node)
        
        return {'way': way_attribs, 'way_nodes': way_nodes, 'way_tags': tags}

# Validating element to match schema
def validate_element(element, validator, schema=SCHEMA):
    """Raise ValidationError if element does not match schema"""
    if validator.validate(element, schema) is not True:
        field, errors = next(validator.errors.iteritems())
        message_string = "\nElement of type '{0}' has the following errors:\n{1}"
        error_strings = (
            "{0}: {1}".format(k, v if isinstance(v, str) else ", ".join(v))
            for k, v in errors.iteritems()
        )
        raise cerberus.ValidationError(
            message_string.format(field, "\n".join(error_strings))
        )


# Extend csv.DictWriter to handle Unicode input
class UnicodeDictWriter(csv.DictWriter, object):
    def writerow(self, row):
        super(UnicodeDictWriter, self).writerow({
            k: (v.encode('utf-8') if isinstance(v, unicode) else v) for k, v in row.iteritems()
        })

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)
            
# Main function processing osm file to 5 csv files
def process_map(file_in, validate):
    """Iteratively process each XML element and write to csv(s)"""

    with codecs.open(NODES_PATH, 'w') as nodes_file, \
         codecs.open(NODE_TAGS_PATH, 'w') as nodes_tags_file, \
         codecs.open(WAYS_PATH, 'w') as ways_file, \
         codecs.open(WAY_NODES_PATH, 'w') as way_nodes_file, \
         codecs.open(WAY_TAGS_PATH, 'w') as way_tags_file:

        nodes_writer = UnicodeDictWriter(nodes_file, NODE_FIELDS)
        node_tags_writer = UnicodeDictWriter(nodes_tags_file, NODE_TAGS_FIELDS)
        ways_writer = UnicodeDictWriter(ways_file, WAY_FIELDS)
        way_nodes_writer = UnicodeDictWriter(way_nodes_file, WAY_NODES_FIELDS)
        way_tags_writer = UnicodeDictWriter(way_tags_file, WAY_TAGS_FIELDS)

        nodes_writer.writeheader()
        node_tags_writer.writeheader()
        ways_writer.writeheader()
        way_nodes_writer.writeheader()
        way_tags_writer.writeheader()

        validator = cerberus.Validator()

        for element in get_element(file_in, tags=('node', 'way')):
            el = shape_element(element)
            if el:
                if validate is True:
                    validate_element(el, validator)

                if element.tag == 'node':
                    nodes_writer.writerow(el['node'])
                    node_tags_writer.writerows(el['node_tags'])
                elif element.tag == 'way':
                    ways_writer.writerow(el['way'])
                    way_nodes_writer.writerows(el['way_nodes'])
                    way_tags_writer.writerows(el['way_tags'])
                    
# Note: Validation is ~ 10X slower. Consider using a small
# sample of the map when validating.
process_map(osm_file_3, validate=True)

