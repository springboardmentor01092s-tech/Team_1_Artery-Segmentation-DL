"""Source-bound documentation counts, never anatomical or qualification coverage."""
from app.schemas.annotation_draft import POINT_FIELDS


def review_coverage(source,protocol,parents):
    readers=[]
    for index,parent in enumerate(parents):
        doc=parent['submission']['document'];lesions=doc['lesions']
        readers.append({'slot':f'R{index+1}','submission_sha256':parent['record_sha256'],
            'case_disposition':doc['case_disposition'],'recorded_lesion_rows':len(lesions),
            'landmarks_recorded':sum(row[field] is not None for row in lesions for field in POINT_FIELDS),
            'landmark_fields':len(POINT_FIELDS)*len(lesions),
            'manual_diameters_recorded':sum(row[field] is not None for row in lesions for field in ['minimum_lumen_diameter_mm','adjacent_reference_diameter_mm']),
            'qualification_status':'not_established','independence_status':'not_established'})
    return {'schema_version':'review-documentation-coverage/0.1','case_id':source['case_id'],
        'source_sha256':source['source_sha256'],'protocol_version':protocol,
        'scope':'recorded_fields_not_anatomical_coverage_or_correctness','readers':readers,
        'external_packet_status':'not_bound','evidence_receipts_status':'not_verified','protocol_signoff_status':'not_verified',
        'clinical_gate_authorized':False,'training_release_authorized':False}
