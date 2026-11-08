# Verify these five against the official PDFs

Phase 2, Part F. One program per school, the largest in each, chosen in
`DECISIONS.md`. Every rule is printed next to the exact line of the
requirement PDF it was read from, so a check needs the PDF and this file
and nothing else.

**What to do.** Open each program's `Source` link, read down the table, and
say which programs are right. Claude Code then sets `"tier": "verified"`
in those `data/programs/{CODE}.json` files — nothing else sets that tier.

One exception to the `Source` link: the School Requirements are published
in a separate PDF, so that group names its own URL and is not in the
program's PDF at all.

Two of the five are track variants rather than the base program, because
`BSc in Mathematics` and `BSc in Global China Studies` both require the
student to choose a track, so the base on its own is not a plannable
program (`tier: unsupported`). `MATH-AM` and `GCS-SS` stand in for them.

A `caveat` is a condition the PDF states that no rule type can enforce; it
is shown to the student rather than checked. Worth reading, but it is not
a mistake in the extraction.

---

## COMP — BEng in Computer Science

Source: <https://ugadmin.hkust.edu.hk/prog_crs/ug/202627/pdf/26-27comp.pdf>  
Tier: `auto_extracted` · 3 groups · 15 rules · at least 57 credits · states 120 for the degree

### Engineering Fundamental Course(s)  _(Major)_

| # | What the data says | The line it came from |
|---|---|---|
| 1 | must take COMP 1023 (Introduction to Python Programming, 3 cr) | `COMP | 1023 | Introduction to Python Programming | 3` |
| 2 | must take one of: MATH 1013 (Calculus I, 3 cr) + MATH 1014 (Calculus II, 3 cr)  **OR**  MATH 1013 (Calculus I, 3 cr) + MATH 1024 (Honors Calculus II, 3 cr)  **OR**  MATH 1023 (Honors Calculus I, 3 cr) + MATH 1014 (Calculus II, 3 cr)  **OR**  MATH 1023 (Honors Calculus I, 3 cr) + MATH 1024 (Honors Calculus II, 3 cr)  **OR**  MATH 1020 (Accelerated Calculus, 4 cr) | `MATH | Note: [(MATH 1013 OR MATH 1023) AND (MATH 1014 OR MATH 1024)] OR [MATH 1020] | 4-6` |
| 3 | must take one of: MATH 2111 (Matrix Algebra and Applications, 3 cr)  **OR**  MATH 2121 (Linear Algebra, 4 cr)  **OR**  MATH 2131 (Honors in Linear and Abstract Algebra I, 4 cr) | `MATH | Note: MATH 2111 OR MATH 2121 OR MATH 2131 | 3-4` |

### Required Course(s)  _(Major)_

| # | What the data says | The line it came from |
|---|---|---|
| 1 | must take one of: COMP 1991 (Industrial Experience, 0 cr) + COMP 4981 (Final Year Project, 6 cr)  **OR**  COMP 1991 (Industrial Experience, 0 cr) + COMP 4981H (Final Year Thesis, 6 cr)  **OR**  COMP 4910 (Co-op Program, 6 cr) | `COMP | Note: [COMP 1991 AND (COMP 4981 OR COMP 4981H)] OR [COMP 4910] | 6` |
| 2 | must take one of: COMP 2011 (Programming with C++, 4 cr) + COMP 2012 (Object-Oriented Programming and Data Structures, 4 cr)  **OR**  COMP 2012H (Honors Object-Oriented Programming and Data Structures, 5 cr) | `COMP | Note: (COMP 2011 AND COMP 2012) OR COMP 2012H | 5-8` |
| 3 | must take COMP 2611 (Computer Organization, 4 cr) | `COMP | 2611 | Computer Organization | 4` |
| 4 | must take one of: COMP 2711 (Discrete Mathematical Tools for Computer Science, 4 cr)  **OR**  COMP 2711H (Honors Discrete Mathematical Tools for Computer Science, 4 cr) | `COMP | Note: COMP 2711 OR COMP 2711H | 4` |
| 5 | must take one of: COMP 3111 (Software Engineering, 4 cr)  **OR**  COMP 3111H (Honors Software Engineering, 4 cr) | `COMP | Note: COMP 3111 OR COMP 3111H | 4` |
| 6 | must take COMP 3511 (Operating Systems, 3 cr) | `COMP | 3511 | Operating Systems | 3` |
| 7 | must take one of: COMP 3711 (Design and Analysis of Algorithms, 3 cr)  **OR**  COMP 3711H (Honors Design and Analysis of Algorithms, 4 cr) | `COMP | Note: COMP 3711 OR COMP 3711H | 3-4` |
| 8 | must take COMP 4900 (Academic and Professional Development, 0 cr) in every term in residence | `COMP | Note: Students are required to take COMP 4900 for every regular term in which they are in residency at HKUST with major in COMP | 0` |
| 9 | must take one of: ELEC 2600 (Probability and Random Processes in Engineering, 4 cr)  **OR**  IEDA 2520 (Probability for Engineers, 3 cr)  **OR**  IEDA 2540 (Statistics for Engineers, 3 cr)  **OR**  MATH 2411 (Applied Statistics, 4 cr)  **OR**  MATH 2421 (Probability, 4 cr)  **OR**  MATH 2431 (Honors Probability, 4 cr) | `ELEC/IEDA/MATH | Note: ELEC 2600 OR ELEC 2600H OR IEDA 2520 OR IEDA 2540 OR MATH 2411 OR MATH 2421 OR MATH 2431 | 3-4` |

### Elective(s)  _(Major)_

| # | What the data says | The line it came from |
|---|---|---|
| 1 | at least 3 credits from COMP 2xxx, COMP 3xxx, COMP 4xxx, COMP 5xxx | `COMP | COMP 2000-level or above Elective (Any course(s) of the subject and level as specified) | 3` |
| 2 | must take 5 of these 60: COMP 3211, COMP 3721, COMP 4211, COMP 4212, COMP 4221, COMP 4222, COMP 4331, COMP 4332, COMP 4421, COMP 4471, COMP 4541, COMP 4551, COMP 4901B, COMP 4901D, COMP 4901L, COMP 4901R, COMP 4901T, COMP 4901V, COMP 4901X, COMP 5211, COMP 5212, COMP 5214, COMP 5215, COMP 5221, COMP 5331, COMP 5421, COMP 5711, COMP 5712, COMP 5713, COMP 4411, COMP 4431, COMP 4441, COMP 4451, COMP 4461, COMP 4462, COMP 5411, COMP 3021, COMP 3031, COMP 3311, COMP 4021, COMP 4121, COMP 4321, COMP 4521, COMP 4651, COMP 4901A, COMP 5111, COMP 5112, COMP 5311, COMP 3631, COMP 4531, COMP 4611, COMP 4621, COMP 4632, COMP 4634, COMP 4635, COMP 4641, COMP 4901Q, COMP 5621, COMP 5631, COMP 4911 | `COMP | COMP Electives (5 courses from the specified elective list, of which at least 3 courses should be taken from 1 area and at least 2 courses outside that area (including course(s) in the Courses Without Associated Area). Students may use at most one course under Deep Learning Applications (COMP` |
| 3 | at least 15 credits from COMP 3211, COMP 3721, COMP 4211, COMP 4212, COMP 4221, COMP 4222, COMP 4331, COMP 4332, COMP 4421, COMP 4471, COMP 4541, COMP 4551, COMP 4901B, COMP 4901D, COMP 4901L, COMP 4901R, COMP 4901T, COMP 4901V, COMP 4901X, COMP 5211, COMP 5212, COMP 5214, COMP 5215, COMP 5221, COMP 5331, COMP 5421, COMP 5711, COMP 5712, COMP 5713, COMP 4411, COMP 4431, COMP 4441, COMP 4451, COMP 4461, COMP 4462, COMP 5411, COMP 3021, COMP 3031, COMP 3311, COMP 4021, COMP 4121, COMP 4321, COMP 4521, COMP 4651, COMP 4901A, COMP 5111, COMP 5112, COMP 5311, COMP 3631, COMP 4531, COMP 4611, COMP 4621, COMP 4632, COMP 4634, COMP 4635, COMP 4641, COMP 4901Q, COMP 5621, COMP 5631, COMP 4911 | `COMP | COMP Electives (5 courses from the specified elective list, of which at least 3 courses should be taken from 1 area and at least 2 courses outside that area (including course(s) in the Courses Without Associated Area). Students may use at most one course under Deep Learning Applications (COMP` |

### Caveats (3) — shown, not checked

- COMP Electives (5 courses from the specified elective list, of which at least 3 courses should be taken from 1 area and at least 2 courses outside that area (including course(s) in the Courses Without Associated Area). Students may use at most one course under Deep Learning Applications (COMP 4471 and COMP 5215) to count towards this elective requirement.) -- the credits and the course count are checked, but the extra condition in this sentence is not. Confirm it with your advisor.
- ELEC 2600H: The course was last offered in 2021-22 and was deleted subsequently.
- Required Course(s): ELEC 2600H is named in the requirement PDF but not in the 2026-27 course catalog, so it was left out of this check.

---

## MATH-AM — BSc in Mathematics - Applied Mathematics Track

Source: <https://ugadmin.hkust.edu.hk/prog_crs/ug/202627/pdf/26-27math.pdf>  
Tier: `auto_extracted` · 5 groups · 16 rules · at least 61 credits · states 120 for the degree

### Requirements  _(School)_

Read this group against <https://ugadmin.hkust.edu.hk/prog_crs/ug/202627/pdf/26-27ssci_requirements.pdf>, not the program's own PDF.

| # | What the data says | The line it came from |
|---|---|---|
| 1 | must take one of: COMP 1021 (Introduction to Computer Science, 3 cr)  **OR**  COMP 1023 (Introduction to Python Programming, 3 cr) | `COMP | Note: COMP 1021 OR COMP 1022P OR COMP 1023 | 3` |
| 2 | must take 6 of these 34: CHEM 1008, CHEM 1011, CHEM 1012, CHEM 1051, CHEM 1052, DASC 2010, LIFS 1901, LIFS 1902, LIFS 1903, LIFS 1904, LIFS 1930, LIFS 2210, MATH 1005, MATH 1006, MATH 1013, MATH 1014, MATH 1020, MATH 1023, MATH 1024, MATH 2011, MATH 2023, MATH 2111, MATH 2121, MATH 2131, OCES 1001, OCES 1010, PHYS 1101, PHYS 1111, PHYS 1112, PHYS 1113, PHYS 1114, PHYS 1115, PHYS 1312, PHYS 1314 | `SSCI | Science Foundation courses [6 courses from the specified elective list, including at least 1 lecture course, but no more than 3 courses (including lecture and laboratory courses), from each of the four disciplines: CHEM, LIFS/OCES, MATH/DASC and PHYS.]` |
| 3 | at least 0 credits from CHEM 1008, CHEM 1011, CHEM 1012, CHEM 1051, CHEM 1052, DASC 2010, LIFS 1901, LIFS 1902, LIFS 1903, LIFS 1904, LIFS 1930, LIFS 2210, MATH 1005, MATH 1006, MATH 1013, MATH 1014, MATH 1020, MATH 1023, MATH 1024, MATH 2011, MATH 2023, MATH 2111, MATH 2121, MATH 2131, OCES 1001, OCES 1010, PHYS 1101, PHYS 1111, PHYS 1112, PHYS 1113, PHYS 1114, PHYS 1115, PHYS 1312, PHYS 1314 | `SSCI | Science Foundation courses [6 courses from the specified elective list, including at least 1 lecture course, but no more than 3 courses (including lecture and laboratory courses), from each of the four disciplines: CHEM, LIFS/OCES, MATH/DASC and PHYS.]` |

### Major Pre-requisite course(s)  _(Major)_

| # | What the data says | The line it came from |
|---|---|---|
| 1 | must take one of: MATH 1013 (Calculus I, 3 cr) + MATH 1014 (Calculus II, 3 cr)  **OR**  MATH 1013 (Calculus I, 3 cr) + MATH 1024 (Honors Calculus II, 3 cr)  **OR**  MATH 1023 (Honors Calculus I, 3 cr) + MATH 1014 (Calculus II, 3 cr)  **OR**  MATH 1023 (Honors Calculus I, 3 cr) + MATH 1024 (Honors Calculus II, 3 cr)  **OR**  MATH 1020 (Accelerated Calculus, 4 cr) | `MATH | Note: [(MATH 1013 OR MATH 1023) AND (MATH 1014 OR MATH 1024)] OR [MATH 1020] (Students following IRE track can only use MATH 1023 and MATH 1024 to fulfill the requirement) | 4-6` |

### Required Course(s)  _(Major)_

| # | What the data says | The line it came from |
|---|---|---|
| 1 | must take one of: MATH 2023 (Multivariable Calculus, 4 cr)  **OR**  MATH 2024 (Honors Multivariable Calculus, 4 cr) | `MATH | Note: MATH 2023 OR MATH 2024 [Students following IRE Track or Pure Mathematics (Advanced) Track can only use MATH 2024 to fulfill the requirement.] | 4` |
| 2 | must take one of: MATH 2033 (Mathematical Analysis, 4 cr)  **OR**  MATH 2043 (Honors Mathematical Analysis, 4 cr) | `MATH | Note: MATH 2033 OR MATH 2043 [Students following IRE Track or Pure Mathematics (Advanced) Track can only use MATH 2043 to fulfill the requirement.] | 4` |
| 3 | must take one of: MATH 2121 (Linear Algebra, 4 cr)  **OR**  MATH 2131 (Honors in Linear and Abstract Algebra I, 4 cr) | `MATH | Note: MATH 2121 OR MATH 2131 [Students following IRE Track or Pure Mathematics (Advanced) Track can only use MATH 2131 to fulfill the requirement.] | 4` |
| 4 | must take one of: MATH 3033 (Real Analysis, 4 cr)  **OR**  MATH 3043 (Honors Real Analysis, 4 cr) | `MATH | Note: MATH 3033 OR MATH 3043 [Students following IRE Track or Pure Mathematics (Advanced) Track can only use MATH 3043 to fulfill the requirement.] | 4` |

### Applied Mathematics Track - Required Course(s)  _(Major)_

| # | What the data says | The line it came from |
|---|---|---|
| 1 | must take MATH 2352 (Differential Equations, 4 cr) | `MATH | 2352 | Differential Equations | 4` |
| 2 | must take MATH 2411 (Applied Statistics, 4 cr) | `MATH | 2411 | Applied Statistics | 4` |
| 3 | must take MATH 3312 (Numerical Analysis, 3 cr) | `MATH | 3312 | Numerical Analysis | 3` |
| 4 | must take MATH 4052 (Partial Differential Equations, 3 cr) | `MATH | 4052 | Partial Differential Equations | 3` |
| 5 | must take MATH 4360 (Mathematical Modeling, 3 cr) | `MATH | 4360 | Mathematical Modeling | 3` |
| 6 | must take one of: MATH 4992 (Capstone Project in Applied Mathematics, 3 cr)  **OR**  MATH 4999 (Independent Capstone Project, 3 cr) | `MATH | Note: MATH 4992 OR MATH 4999 | 3` |

### Applied Mathematics Track - Elective Course(s)  _(Major)_

| # | What the data says | The line it came from |
|---|---|---|
| 1 | must take 4 of these 17: MATH 2001, MATH 2421, MATH 2431, MATH 3322, MATH 3332, MATH 3425, MATH 4023, MATH 4051, MATH 4321, MATH 4326, MATH 4335, MATH 4336, MATH 4343, MATH 4351, MATH 4511, MATH 4512, MATH 4823 | `MATH | MATH Depth Electives (4 courses from the specified elective list) | 12` |
| 2 | at least 12 credits from MATH 2001, MATH 2421, MATH 2431, MATH 3322, MATH 3332, MATH 3425, MATH 4023, MATH 4051, MATH 4321, MATH 4326, MATH 4335, MATH 4336, MATH 4343, MATH 4351, MATH 4511, MATH 4512, MATH 4823 | `MATH | MATH Depth Electives (4 courses from the specified elective list) | 12` |

### Caveats (7) — shown, not checked

- Students MUST take the following courses prior to enrollment into the major
- [(MATH 1013 OR MATH 1023) AND (MATH 1014 OR MATH 1024)] OR [MATH 1020] -- (Students following IRE track can only use MATH 1023 and MATH 1024 to fulfill the requirement)
- MATH 2023 OR MATH 2024 -- [Students following IRE Track or Pure Mathematics (Advanced) Track can only use MATH 2024 to fulfill the requirement.]
- MATH 2033 OR MATH 2043 -- [Students following IRE Track or Pure Mathematics (Advanced) Track can only use MATH 2043 to fulfill the requirement.]
- MATH 2121 OR MATH 2131 -- [Students following IRE Track or Pure Mathematics (Advanced) Track can only use MATH 2131 to fulfill the requirement.]
- MATH 3033 OR MATH 3043 -- [Students following IRE Track or Pure Mathematics (Advanced) Track can only use MATH 3043 to fulfill the requirement.]
- Requirements: COMP 1022P is named in the requirement PDF but not in the 2026-27 course catalog, so it was left out of this check.

---

## FINA — BBA in Finance

Source: <https://ugadmin.hkust.edu.hk/prog_crs/ug/202627/pdf/26-27fina.pdf>  
Tier: `auto_extracted` · 3 groups · 20 rules · at least 55 credits · states 120 for the degree

### Requirements  _(School)_

Read this group against <https://ugadmin.hkust.edu.hk/prog_crs/ug/202627/pdf/26-27sbm_requirements.pdf>, not the program's own PDF.

| # | What the data says | The line it came from |
|---|---|---|
| 1 | must take ACCT 2010 (Principles of Accounting I, 3 cr) | `ACCT | 2010 | Principles of Accounting I | 3` |
| 2 | must take one of: ECON 2103 (Principles of Microeconomics, 3 cr)  **OR**  ECON 2113 (Microeconomics, 3 cr) | `ECON | Note: ECON 2103 OR ECON 2113 | 3` |
| 3 | must take one of: ECON 2123 (Macroeconomics, 3 cr)  **OR**  ECON 3123 (Macroeconomic Theory I, 3 cr) | `ECON | Note: ECON 2123 OR ECON 3123 (BSc ECOF students can only use ECON 3123 to fulfill this requirement; while others should take ECON 2123) | 3` |
| 4 | must take FINA 2303 (Financial Management, 3 cr) | `FINA | 2303 | Financial Management | 3` |
| 5 | must take ISOM 2010 (Introduction to Information Systems, 3 cr) | `ISOM | 2010 | Introduction to Information Systems | 3` |
| 6 | must take ISOM 2020 (Coding for Business, 1 cr) | `ISOM | 2020 | Coding for Business | 1` |
| 7 | must take ISOM 2500 (Business Statistics, 3 cr) | `ISOM | 2500 | Business Statistics | 3` |
| 8 | must take ISOM 2600 (Introduction to Business Analytics, 1 cr) | `ISOM | 2600 | Introduction to Business Analytics | 1` |
| 9 | must take MGMT 2010 (Business Ethics and the Individual, 2 cr) | `MGMT | 2010 | Business Ethics and the Individual | 2` |
| 10 | must take MGMT 2130 (Business Ethics and Social Responsibility, 2 cr) | `MGMT | 2130 | Business Ethics and Social Responsibility | 2` |
| 11 | must take one of: MATH 1003 (Calculus and Linear Algebra, 3 cr)  **OR**  MATH 1013 (Calculus I, 3 cr)  **OR**  MATH 1020 (Accelerated Calculus, 4 cr)  **OR**  MATH 1023 (Honors Calculus I, 3 cr) | `MATH | Note: MATH 1003 OR MATH 1013 OR MATH 1020 OR MATH 1023 | 3-4` |
| 12 | must take ACCT 2200 (Principles of Accounting II, 3 cr); ISOM 2700 (Operations Management, 3 cr); MARK 2120 (Marketing Management, 3 cr); MGMT 2110 (Organizational Behavior, 3 cr) | `SB&M | Note: Courses for BBA majors: ACCT 2200 AND ISOM 2700 AND MARK 2120 AND MGMT 2110 (Students who enroll in the BSc majors of SBM are not required to take these courses for graduation) | 12` |

### Required Course(s)  _(Major)_

| # | What the data says | The line it came from |
|---|---|---|
| 1 | must take FINA 3001 (Key Skills for Finance Professionals (A), 1 cr) | `FINA | 3001 | Key Skills for Finance Professionals (A) | 1` |
| 2 | must take FINA 3103 (Intermediate Investments, 3 cr) | `FINA | 3103 | Intermediate Investments | 3` |
| 3 | must take FINA 3203 (Derivative Securities, 3 cr) | `FINA | 3203 | Derivative Securities | 3` |
| 4 | must take FINA 3303 (Intermediate Corporate Finance, 3 cr) | `FINA | 3303 | Intermediate Corporate Finance | 3` |
| 5 | must take FINA 3810 (Bloomberg Market Concepts Certification, 0 cr) | `FINA | 3810 | Bloomberg Market Concepts Certification | 0` |
| 6 | must take one of: ACCT 3010 (Financial Accounting I, 3 cr) + ACCT 3020 (Financial Accounting II, 3 cr)  **OR**  ACCT 3030 (Intermediate Financial Accounting for Non-Accounting Majors, 3 cr) | `ACCT | Note: (ACCT 3010 AND ACCT 3020) OR ACCT 3030 | 3-6` |
| 7 | must take one of: ISOM 3230 (Business Programming in VBA, 3 cr)  **OR**  ISOM 3320 (Business Applications Development in Java, 3 cr)  **OR**  ISOM 3400 (Business Applications Development in Python, 3 cr)  **OR**  COMP 1023 (Introduction to Python Programming, 3 cr) | `ISOM/COMP | Note: ISOM 3230 OR ISOM 3320 OR ISOM 3400 OR COMP 1023 | 3` |

### Elective(s)  _(Major)_

| # | What the data says | The line it came from |
|---|---|---|
| 1 | at least 9 credits from FINA 3xxx, FINA 4xxx, FINA 5xxx | `FINA | FINA 3000-level or above Electives (Any 3 courses of the subject and level as specified) | 9` |

---

## GCS-SS — BSc in Global China Studies - Social Science Track

Source: <https://ugadmin.hkust.edu.hk/prog_crs/ug/202627/pdf/26-27gcs.pdf>  
Tier: `auto_extracted` · 3 groups · 14 rules · at least 39 credits · states 120 for the degree

### Required Course(s)  _(Major)_

| # | What the data says | The line it came from |
|---|---|---|
| 1 | must take HUMA 1440 (Modern China, 3 cr) | `HUMA | 1440 | Modern China | 3` |
| 2 | must take HUMA 2590 (The Making of the Modern World: Renaissance to the Present, 3 cr) | `HUMA | 2590 | The Making of the Modern World: Renaissance to the Present | 3` |
| 3 | must take SOSC 1350 (Contemporary China: Continuity and Change, 3 cr) | `SOSC | 1350 | Contemporary China: Continuity and Change | 3` |
| 4 | must take SOSC 2290 (Understanding Globalization, 3 cr) | `SOSC | 2290 | Understanding Globalization | 3` |
| 5 | must take one of: SHSS 4991 (Capstone Project, 3 cr)  **OR**  SHSS 4992 (Honors Thesis, 6 cr)  **OR**  SHSS 4991 (Capstone Project, 3 cr) + SHSS 4993 (Honors Research, 3 cr) | `SHSS | Note: SHSS 4991 OR SHSS 4992 OR (SHSS 4991 AND SHSS 4993) [For students taking one of the Research Options, they should take SHSS 4992 OR (SHSS 4991 AND SHSS 4993)] | 3-6` |
| 6 | must take LANG 2170 (Chinese Communication Skills for Humanities & Social Science Studies, 3 cr) | `LANG | 2170 | Chinese Communication Skills for Humanities & Social Science Studies | 3` |

### Social Science Track - Required Course(s)  _(Major)_

| # | What the data says | The line it came from |
|---|---|---|
| 1 | must take SOSC 1100 (Quantitative Data Analysis for Social Research I, 3 cr) | `SOSC | 1100 | Quantitative Data Analysis for Social Research I | 3` |
| 2 | must take SOSC 1300 (The World of Politics, 3 cr) | `SOSC | 1300 | The World of Politics | 3` |
| 3 | must take SOSC 1440 (Introduction to Economics, 3 cr) | `SOSC | 1440 | Introduction to Economics | 3` |
| 4 | must take SOSC 1850 (Understanding Society, 3 cr) | `SOSC | 1850 | Understanding Society | 3` |
| 5 | must take SOSC 2140 (Research Methods in the Social Sciences, 3 cr) | `SOSC | 2140 | Research Methods in the Social Sciences | 3` |

### Social Science Track - Elective Course(s)  _(Major)_

| # | What the data says | The line it came from |
|---|---|---|
| 1 | must take 2 of these 4: SOSC 1780, SOSC 1860, SOSC 1960, SOSC 1980 | `SOSC | Disciplinary Foundation Electives (2 courses from the specified elective list, of which the courses should be taken from different areas.) | 6
  [Introductory Demography]
  [Introductory Psychology]` |
| 2 | at least 6 credits from SOSC 1780, SOSC 1860, SOSC 1960, SOSC 1980 | `SOSC | Disciplinary Foundation Electives (2 courses from the specified elective list, of which the courses should be taken from different areas.) | 6
  [Introductory Demography]
  [Introductory Psychology]` |
| 3 | at least 27 credits from SOSC 3120, SOSC 3520, SOSC 3540, SOSC 3630, SOSC 3880, SOSC 4260, SOSC 4280, SOSC 4310, SOSC 4600, SOSC 1xxx, SOSC 2xxx, SOSC 3xxx, SOSC 4xxx, SOSC 5xxx | `SOSC | SOSC Electives (9 courses from the specified elective list, of which at least 4 courses must come from the list under "Restricted Electives".) | 27
  [Restricted Electives]
  [Others]
  SOSC | Any SOSC courses` |

### Caveats (4) — shown, not checked

- SHSS 4991 OR SHSS 4992 OR (SHSS 4991 AND SHSS 4993) -- [For students taking one of the Research Options, they should take SHSS 4992 OR (SHSS 4991 AND SHSS 4993)]
- SOSC Electives (9 courses from the specified elective list, of which at least 4 courses must come from the list under "Restricted Electives".) -- the list also admits any SOSC course, so the credits are checked but the number of courses is not. Confirm the count with your advisor.
- SOSC 4290: The course was last offered in 2023-24 and was deleted subsequently.
- Social Science Track - Elective Course(s): SOSC 4290 is named in the requirement PDF but not in the 2026-27 course catalog, so it was left out of this check.

---

## IDT — BSc in Innovation, Design and Technology

Source: <https://ugadmin.hkust.edu.hk/prog_crs/ug/202627/pdf/26-27idt.pdf>  
Tier: `auto_extracted` · 2 groups · 27 rules · at least 84 credits · states 120 for the degree

### Required Course(s)  _(Major)_

| # | What the data says | The line it came from |
|---|---|---|
| 1 | must take ISDN 1001 (Introduction to Integrative Systems and Design, 3 cr) | `ISDN | 1001 | Introduction to Integrative Systems and Design | 3` |
| 2 | must take ISDN 1004 (Sketching, 1 cr) | `ISDN | 1004 | Sketching | 1` |
| 3 | must take ISDN 1007 (From Design Thinking to Design Action: Defining Problems for Better Solutions, 3 cr) | `ISDN | 1007 | From Design Thinking to Design Action: Defining Problems for Better Solutions | 3` |
| 4 | must take ISDN 1010 (Academic and Professional Development I, 0 cr) | `ISDN | 1010 | Academic and Professional Development I | 0` |
| 5 | must take ISDN 1011 (Industrial Training, 0 cr) | `ISDN | 1011 | Industrial Training | 0` |
| 6 | must take ISDN 2001 (Second Year Design Project I, 1 cr) | `ISDN | 2001 | Second Year Design Project I | 1` |
| 7 | must take ISDN 2002 (Second Year Design Project II, 3 cr) | `ISDN | 2002 | Second Year Design Project II | 3` |
| 8 | must take ISDN 2010 (Academic and Professional Development II, 0 cr) | `ISDN | 2010 | Academic and Professional Development II | 0` |
| 9 | must take ISDN 2200 (Systems Thinking and Design, 3 cr) | `ISDN | 2200 | Systems Thinking and Design | 3` |
| 10 | must take ISDN 2300 (Introduction to 3D Design, 3 cr) | `ISDN | 2300 | Introduction to 3D Design | 3` |
| 11 | must take ISDN 2400 (Physical Prototyping, 3 cr) | `ISDN | 2400 | Physical Prototyping | 3` |
| 12 | must take ISDN 2601 (Exploring the World through Smart Mechatronics, 3 cr) | `ISDN | 2601 | Exploring the World through Smart Mechatronics | 3` |
| 13 | must take ISDN 2602 (Internet of Things: Integrative System Design, 3 cr) | `ISDN | 2602 | Internet of Things: Integrative System Design | 3` |
| 14 | must take ISDN 2603 (Materials, Shape and Design, 3 cr) | `ISDN | 2603 | Materials, Shape and Design | 3` |
| 15 | must take ISDN 3001 (Third Year Design Project I, 3 cr) | `ISDN | 3001 | Third Year Design Project I | 3` |
| 16 | must take ISDN 3002 (Third Year Design Project II, 3 cr) | `ISDN | 3002 | Third Year Design Project II | 3` |
| 17 | must take ISDN 3010 (Academic and Professional Development III, 0 cr) | `ISDN | 3010 | Academic and Professional Development III | 0` |
| 18 | must take ISDN 3200 (Graphic Communication, 2 cr) | `ISDN | 3200 | Graphic Communication | 2` |
| 19 | must take ISDN 4001 (Final Year Design Project I, 4 cr) | `ISDN | 4001 | Final Year Design Project I | 4` |
| 20 | must take ISDN 4002 (Final Year Design Project II, 4 cr) | `ISDN | 4002 | Final Year Design Project II | 4` |
| 21 | must take ISDN 4010 (Academic and Professional Development IV, 0 cr) | `ISDN | 4010 | Academic and Professional Development IV | 0` |
| 22 | must take one of: COMP 1023 (Introduction to Python Programming, 3 cr)  **OR**  COMP 2011 (Programming with C++, 4 cr)  **OR**  COMP 2012H (Honors Object-Oriented Programming and Data Structures, 5 cr) | `COMP | Note: COMP 1023 OR COMP 2011 OR COMP 2012H | 3-5` |
| 23 | must take LANG 4036 (Technical Communication for Technology Projects, 3 cr) | `LANG | 4036 | Technical Communication for Technology Projects | 3` |
| 24 | must take one of: MATH 1006 (Calculus, Vectors, and Matrices, 4 cr)  **OR**  MATH 1013 (Calculus I, 3 cr)  **OR**  MATH 1023 (Honors Calculus I, 3 cr) + MATH 1014 (Calculus II, 3 cr)  **OR**  MATH 1023 (Honors Calculus I, 3 cr) + MATH 1024 (Honors Calculus II, 3 cr)  **OR**  MATH 1020 (Accelerated Calculus, 4 cr) | `MATH | Note: [MATH 1006 OR MATH 1013 OR MATH 1023 AND (MATH 1014 OR MATH 1024)] OR [MATH 1020] (Subject to approval of the program office, MATH 1014/1024 may be replaced by a COMP course) | 4-7` |
| 25 | must take one of: PHYS 1101 (Introductory Physics, 4 cr)  **OR**  PHYS 1111 (General Physics I, 3 cr)  **OR**  PHYS 1112 (General Physics I with Calculus, 3 cr)  **OR**  PHYS 1312 (Honors General Physics I, 3 cr) | `PHYS | Note: PHYS 1101 OR PHYS 1111 OR PHYS 1112 OR PHYS 1312 | 3-4` |

### Elective(s)  _(Major)_

| # | What the data says | The line it came from |
|---|---|---|
| 1 | at least 6 credits from ISDN 3350, ISDN 3360, ISDN 4200, ENTR 3100, FINA 2203, ISOM 2030, ISOM 2700, ISOM 4020, MARK 2120, TEMG 3950, TEMG 4940, TEMG 4950, TEMG 4970 | `ISDN/ENTR/SBM/TEMG | Product Management and Entrepreneurship Electives (Courses from the specified elective list, of which at least 1 course must be at 3000-level or above.) | 6` |
| 2 | at least 21 credits from ISDN 2210, ISDN 3004, ISDN 3150, ISDN 3300, BIEN 3320, COMP 2011, COMP 2012, COMP 2211, COMP 2611, COMP 3111, COMP 3211, COMP 3311, COMP 3711, COMP 4021, COMP 4221, COMP 4331, COMP 4411, COMP 4421, COMP 4461, COMP 4462, COMP 4521, COMP 4632, COMP 4641, COMP 4651, COMP 4901, ELEC 2100, ELEC 2350, ELEC 2400, ELEC 2600, IEDA 2520, MATH 2011, MATH 2111, MATH 2343, MATH 2350, MATH 2411, MECH 2020, MECH 2040, MECH 2210, MECH 2310, MECH 2410, MECH 2520, MECH 3030, MECH 3300, MECH 3310, MECH 3420, MECH 3510, MECH 3610, MECH 3907, MECH 4450, MECH 4710, MECH 4740, ELEC 3xxx, ELEC 4xxx | `ISDN/SENG/MATH | Project-related Electives (Courses from the specified elective list, of which at least 12 credits should be at 3000-level or above and no more than 3 credits at 1000-level. Students should seek approval of their advisor for the choices of courses.) | 21
  ELEC | Any ELEC courses at ` |

### Caveats (1) — shown, not checked

- [MATH 1006 OR MATH 1013 OR MATH 1023 AND (MATH 1014 OR MATH 1024)] OR [MATH 1020] -- (Subject to approval of the program office, MATH 1014/1024 may be replaced by a COMP course)

---
