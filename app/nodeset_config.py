"""Read NodeSet values, metadata and the file's embedded simulator JSON."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from .schemas import NodePatternConfig

NS = {'ua': 'http://opcfoundation.org/UA/2011/03/UANodeSet.xsd',
      'uax': 'http://opcfoundation.org/UA/2008/02/Types.xsd'}


def read_nodeset(path: Path) -> tuple[list[dict], dict[str, NodePatternConfig]]:
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    root = ET.fromstring(path.read_text(encoding='utf-8'), parser=parser)
    if root.tag != f"{{{NS['ua']}}}UANodeSet":
        raise ValueError('Expected an OPC-UA UANodeSet XML file')
    overrides = {}
    # The supplied file stores its machine-readable rules in a trailing comment.
    # Parse comments from the complete document (including after the root).
    for _, comment in ET.iterparse(path, events=('comment',)):
        text = comment.text or ''
        if 'SIMULATOR CONFIG' in text:
            offset = text.find('{')
            if offset < 0:
                raise ValueError('SIMULATOR CONFIG comment has no JSON object')
            settings, _ = json.JSONDecoder().raw_decode(text[offset:])
            overrides = {name: NodePatternConfig.model_validate(rule)
                         for name, rule in settings.get('node_overrides', {}).items()}
    aliases = {el.attrib['Alias']: el.text.strip()
               for el in root.findall('ua:Aliases/ua:Alias', NS)}
    variables = {el.attrib['NodeId']: el for el in root.findall('ua:UAVariable', NS)}
    type_names = {'i=1': 'Boolean', 'i=8': 'Int64', 'i=11': 'Double', 'i=6': 'Int32',
                  'i=10': 'Float', 'i=12': 'String'}
    rows = []
    for node_id, el in variables.items():
        refs = el.findall('ua:References/ua:Reference', NS)
        # Properties are metadata, never traffic targets.
        if any(aliases.get(ref.attrib['ReferenceType'], ref.attrib['ReferenceType']) == 'i=46'
               and ref.attrib.get('IsForward', 'true').lower() == 'false' for ref in refs):
            continue
        name = el.attrib['BrowseName'].split(':', 1)[-1]
        value_el = el.find('ua:Value', NS)
        value = None
        data_type = aliases.get(el.attrib.get('DataType'), el.attrib.get('DataType', ''))
        data_type = type_names.get(data_type, data_type)
        if value_el is not None and len(value_el):
            typed = next((child for child in value_el if isinstance(child.tag, str)), None)
            if typed is not None:
                scalar_type = typed.tag.rsplit('}', 1)[-1]
                text = typed.text or ''
                if scalar_type == 'Boolean':
                    value = text.strip().lower() in ('true', '1')
                elif scalar_type in ('Double', 'Float'):
                    value = float(text)
                elif scalar_type in ('SByte', 'Byte', 'Int16', 'UInt16', 'Int32', 'UInt32', 'Int64', 'UInt64'):
                    value = int(text)
                elif scalar_type == 'String':
                    value = text
        low = high = None
        unit = ''
        for ref in refs:
            if ref.attrib.get('IsForward', 'true').lower() == 'false':
                continue
            prop = variables.get((ref.text or '').strip())
            if prop is None:
                continue
            prop_name = prop.attrib['BrowseName'].split(':', 1)[-1]
            if prop_name == 'EURange' or (prop_name == 'InstrumentRange' and low is None):
                range_el = prop.find('.//uax:Range', NS)
                if range_el is not None:
                    low = float(range_el.findtext('uax:Low', namespaces=NS))
                    high = float(range_el.findtext('uax:High', namespaces=NS))
            if prop_name == 'EngineeringUnits':
                unit = prop.findtext('.//uax:DisplayName/uax:Text', default='', namespaces=NS)
        rule = overrides.get(name)
        if low is None and rule and rule.pattern == 'counter':
            low, high = rule.counter_min, rule.counter_max
        rows.append(dict(name=name, node_id=node_id, data_type=data_type,
                         initial_value=value, value=value, min_value=low, max_value=high,
                         unit=unit, pattern=rule.pattern if rule else 'global',
                         writable=bool(int(el.attrib.get('AccessLevel', '1')) & 2),
                         quality='Loaded', timestamp=None))
    if not rows:
        raise ValueError('NodeSet contains no data tags')
    unknown = set(overrides) - {row['name'] for row in rows}
    if unknown:
        raise ValueError(f'Simulation rules reference unknown tags: {sorted(unknown)}')
    return rows, overrides
