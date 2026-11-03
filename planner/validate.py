"""Full plan validation (Phase 3).

Every check returns errors (blocking) and warnings (non-blocking), each with a
plain-English message plus the course or term it refers to:

  unknown_courses   HKUST codes not in the catalog; slots and exchange rows
                    are exempt                                        -> error
  check_prereqs     prerequisites sit in an earlier term, or transfer  -> error
  check_exclusions  no two mutually exclusive courses                 -> error
  check_offering    offered in that term; no offering data            -> warning
  check_load        per regular term inside the student min-max and inside the
                    regulations.json limits                           -> error
                    regulation unknown and term under 12 credits      -> warning
  check_heavy_terms terms at 18+ credits with a high GPA target       -> warning
  check_exchange    no HKUST courses in exchange terms; exchange credits listed
                    as pending; every_term rules not required while away;
                    requirements met only via exchange                -> warning
  check_free_terms  terms the student asked to keep free are empty     -> error
                    a free final term means graduating early          -> info
  check_spread      front-loaded, back-loaded or even as requested    -> warning
  check_fyp         FYP placement against the regulation              -> warning
  check_transfer    unspecified transfer counts only as free electives; mapped
                    transfers must exist in the catalog               -> error
  check_every_term  every_term rules hold for all terms in residence
  evaluate + total_credits >= 120 and any programme total             -> error
                    an exchange-pending shortfall                     -> warning

validate_plan(plan, profile) -> ValidationReport runs all of the above.

Thresholds come from data/regulations.json with a source URL. If a value is
unknown the check says "verify" -- it never invents a number.
"""


def validate_plan(plan, profile):
    raise NotImplementedError("Phase 3")
