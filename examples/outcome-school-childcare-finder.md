# Outcome Example: School And Childcare Finder

Build a family-oriented discovery tool around schools, childcare centres, student care, and nearby social support.

## User Job

"Show schools, childcare, and student care options around Tampines."

## Recommended Flow

1. Use `sg_query` when the caller starts with a plain-language location:

```text
sg_query {
  "query": "Find childcare vacancies and student care near Tampines",
  "mode": "execute"
}
```

2. Use direct tools when the UI already has structured filters:

```text
sg_moe_schools { "planningArea": "Tampines" }
sg_ecda_childcare_centres { "planningArea": "Tampines" }
sg_msf_student_care_services { "planningArea": "Tampines", "scfaOnly": true }
sg_msf_family_services { "planningArea": "Tampines" }
```

3. Add community context if the user asks for nearby facilities:

```text
sg_civic_brief {
  "planningArea": "Tampines",
  "modules": ["pa", "sportsg", "ecda", "msf"],
  "format": "json"
}
```

## Product Shape

- Filter sidebar: level, service type, planning area, SCFA-only.
- Results list: name, address, phone, source, and freshness.
- Support panel: family services and social service offices when the user asks for help, not as a hidden recommendation.

## Boundaries

Do not imply admission chances, school quality, or childcare availability beyond the returned public records.
