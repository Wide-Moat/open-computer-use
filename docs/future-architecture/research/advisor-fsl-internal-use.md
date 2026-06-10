<!-- SPDX-License-Identifier: FSL-1.1-Apache-2.0 -->
<!-- Copyright (c) 2025 Open Computer Use Contributors -->

---
status: research-buffer
last-reviewed: 2026-05-24
owner: licensing
applies-to: docs/architecture/manifesto/05-licensing-posture.md
---

# FSL-1.1-Apache-2.0 in enterprise / multi-entity deployments — advisor

Advises the FSL clarification that needs to land in
`manifesto/05-licensing-posture.md` (and a sibling `LICENSE-ADDITIONAL-PERMISSIONS.md`
at repo root) so tier-1 bank Legal can clear multi-entity deployments on the first
redline pass instead of the third.

## How FSL-1.1-Apache-2.0 stock text actually reads

Canonical template: [Sentry's fsl.software repo](https://github.com/getsentry/fsl.software/blob/main/FSL-1.1-ALv2.template.md).
Two clauses collide for enterprise readers.

**Permitted Purpose** (verbatim): "A Permitted Purpose is any purpose other than a
Competing Use. […] Permitted Purposes specifically include using the Software:
1. for your internal use and access; 2. for non-commercial education;
3. for non-commercial research; and 4. in connection with professional services
that you provide to a licensee using the Software in accordance with these Terms
and Conditions."

**Competing Use** (verbatim): "A Competing Use means making the Software available
to others in a commercial product or service that: 1. substitutes for the Software;
2. substitutes for any other product or service we offer using the Software that
exists as of the date we make the Software available; or 3. offers the same or
substantially similar functionality as the Software."

Bank Legal will flag two ambiguities. First, the licence defines neither "you"
nor "internal use" — when a holding company licenses software, does "internal"
extend to majority-owned subsidiaries? To joint ventures? To outsourced operators?
The text is silent. Sentry's own issue tracker
([getsentry/fsl.software#13](https://github.com/getsentry/fsl.software/issues/13))
records that self-hosting "is a Permitted Purpose under 1, [but] it is also a
Competing Use under 1 and 2" and the maintainers have not landed a resolution.
Second, professional-services Permitted Purpose 4 requires the *recipient* to be
a "licensee using the Software" — a contractor running the platform for a
non-licensee bank arguably fails that test.

For generic OSS these are footnotes. For a platform aimed at US/EU banks they
are deal-stoppers: regulated entities cannot deploy software whose scope their
own counsel cannot bound.

## Comparable adopters and their experience

| Adopter | Posture | Public clarification | Lesson for Wide-Moat |
|---|---|---|---|
| **Sentry** (FSL author) | Stock FSL | Blog post + one-page [licensing index](https://open.sentry.io/licensing/); contact `oss@sentry.io` for edge cases. No addendum. ([blog](https://blog.sentry.io/introducing-the-functional-source-license-freedom-without-free-riding/)) | Even the licence author triages by email; Wide-Moat cannot scale that for banks. |
| **Liquibase** (2025) | Stock FSL + product split | Community under FSL, Secure under separate commercial licence; FAQ says enterprise daily use is unchanged. ([FAQ](https://docs.liquibase.com/community/user-guide-5-0/faq)) | Two-edition split sidesteps the question by routing enterprise to a commercial contract. Out of scope for v1. |
| **Keygen** | Rejected FSL → Fair Core | "FSL had the same fundamental problem for businesses that wanted to monetize via SaaS but also via a commercial self-hosted edition." ([blog](https://keygen.sh/blog/keygen-is-now-fair-source/)) | FSL's lack of a community/enterprise separator was the dealbreaker — not the multi-entity gap, which remains unaddressed. |
| **PowerSync** | Stock FSL, no addendum | Hosts FSL text verbatim on `powersync.com/legal/fsl`. ([source](https://www.powersync.com/legal/fsl)) | Vanilla adoption is the market default; nobody has solved the multi-entity question yet. First mover sets the template. |
| **Apache Foundation** (Fineract) | External legal review | [LEGAL-721](https://issues.apache.org/jira/browse/LEGAL-721) — Apache Legal had to rule formally on FSL-licensed Liquibase 5 inside ASF projects; result was "non-OSI, not Category A/B." | Sophisticated downstream Legal teams will not interpret on their own; they demand written rulings. Bank Legal will be at least as cautious. |

No adopter ships a published Additional Permissions instrument yet. That is the gap.

## Six options compared

| Option | Legal certainty for bank Legal | Redline cycles avoided | Moat preservation | OSS-funnel preservation | Maintenance cost | Comparable adopters |
|---|---|---|---|---|---|---|
| 1. Stock FSL, no clarifications | Low — each bank re-derives scope | None | Full | Full | Zero | Sentry, PowerSync (slow enterprise cycles) |
| 2. Stock FSL + public FAQ | Low-medium — non-binding reference | Some (first round) | Full | Full | Low (one page, annual review) | Sentry, Liquibase |
| 3. **Stock FSL + published Additional Permissions instrument** at repo root, irrevocable, applying to all licensees | High — binding grant, enumerated scope | Most (Legal has one artifact to redline) | Full (Competing Use clause preserved verbatim) | Full (still FSL, still 2-yr Apache conversion) | Low-medium (one document, one drafting review) | None public yet — Wide-Moat first |
| 4. Stock FSL + per-customer side letter | Highest for the signer; zero for others | None for unsigned; most for signed | Full | Full | High (per-deal Legal work) | Sentry triage, most BSL vendors |
| 5. Custom Wide-Moat licence ("Enterprise Edition") | High once vetted; low until then because bespoke | Some initially; fewer over time | Full if drafted well | Damaged — loses "known fair-source standard" credibility | High (ongoing Legal liability) | BSL/ELv2 vendors; seen as downgrade post-2024 |
| 6. Switch licence (Elastic v2, AGPL+CLA, Fair Core, BSL) | Varies; AGPL well-understood but doesn't block SaaS; Fair Core needs an edition split we don't have | Mixed | Partial — each replacement weakens at least one axis | Damaged (lose 2-yr Apache conversion) | High (re-license repo, re-sign contributors) | Elastic, MongoDB (community-trust loss) |

## Recommended path + draft text

**Recommendation: Option 3 — Stock FSL + a published Additional Permissions
instrument at repo root.** Only option that delivers binding legal certainty
to bank Legal without weakening the anti-SaaS clause, without forking the
licence, without per-deal Legal cost, and without losing the 2-year Apache
conversion clause. FSL is silent on additional permissions but contract law
does not require it to be loud: the licensor can grant any scope on top of
the licence as long as it does not narrow it. Publishing the grant at repo
root, irrevocable, applying to all licensees of all releases, makes it
self-service for bank Legal. The instrument is small, reviewed once.

**Draft text for `LICENSE-ADDITIONAL-PERMISSIONS.md` at repo root**:

> # Additional Permissions to FSL-1.1-Apache-2.0
>
> Copyright (c) 2025 Open Computer Use Contributors. This instrument is
> irrevocable and applies to every release of the Software licensed under
> FSL-1.1-Apache-2.0 by the copyright holders. It grants permissions in addition
> to, and does not narrow, the rights granted by the Functional Source License,
> Version 1.1, Apache 2.0 Future License. The permissions bind the copyright
> holders' successors and assigns.
>
> ## 1. Affiliated entities
> "You" in the License includes any entity that controls, is controlled by, or
> is under common control with the licensee, where "control" means ownership of
> more than 50% of voting equity or the equivalent right to direct management.
> Deployment for the internal use of any such entity is a Permitted Purpose.
>
> ## 2. Joint ventures and consortiums
> Deployment for the internal use of any joint venture, consortium, or
> equivalent multi-party operating entity in which the licensee or an affiliated
> entity (§1) holds an operational role is a Permitted Purpose.
>
> ## 3. Outsourced operators and managed-service providers
> A third party acting as an operator, outsourced IT provider, or managed-service
> provider under a written contract with the licensee, and running the Software
> solely on behalf of and for the benefit of the licensee or an affiliated
> entity, is exercising the licensee's rights under the License and the licensee's
> professional-services Permitted Purpose. The operator acquires no rights of
> its own beyond those needed to perform the contract.
>
> ## 4. Single-tenant managed deployments
> Operating a hosted instance of the Software exclusively for a single,
> identified private customer under a managed-service contract is a Permitted
> Purpose, provided the offering is not marketed under a name or trade dress
> substantially similar to the Software's name or to any product offered by the
> copyright holders.
>
> ## 5. Internal white-labelling
> Renaming the user interface, documentation, and reporting surfaces of the
> Software to reflect the licensee's brand, solely for internal use by the
> licensee or its affiliated entities, is a Permitted Purpose. Copyright,
> licence, and attribution notices in the source distribution must be preserved.
>
> ## 6. What remains forbidden
> Nothing in this instrument permits a Competing Use as defined in the License.
> Operating a public, multi-tenant, paid hosted service where the value
> proposition substantially substitutes for the Software remains a Competing
> Use and is not licensed. Reselling hosted access to multiple third parties
> under any branding is a Competing Use.
>
> ## 7. Future Apache 2.0 conversion
> On the second anniversary of each release, that release becomes available
> under the Apache License, Version 2.0 per the License's Future License Grant.
> The permissions in this instrument become moot for that release on that date.

**Companion paragraph for `manifesto/05-licensing-posture.md`** (one paragraph
under the FSL principle, pointing to the instrument):

> The repository ships a `LICENSE-ADDITIONAL-PERMISSIONS.md` instrument at
> repository root that enumerates internal-use scope for affiliated entities,
> joint ventures, outsourced operators, single-tenant managed deployments, and
> internal white-labelling. The instrument grants permissions in addition to
> the Functional Source License and does not narrow it. Customer Legal teams
> read the two documents together; no side letter is required for the patterns
> listed there. Patterns outside the instrument require a written grant.

## Edge cases answered

| Edge case | Wide-Moat answer | Enforcing clause |
|---|---|---|
| Bank deploys for itself and a partner bank under a treasury-services contract | Permitted if the partner-bank deployment is operated for the partner's internal use under a managed-service contract held by the licensee bank | §3 (licensee bank acts as operator) |
| Consulting firm deploys for client banks under managed service, not branded as a hosted product | Permitted per-client where each client is a licensee or affiliate; the firm gets no independent rights | §3 (operator on behalf of a licensee client) |
| OSS contributor runs a free public demo instance | Permitted if non-commercial and not branded as a competing product | §6 + FSL non-commercial research/education |
| 2-year-old release is forked and rehosted as paid SaaS | Permitted for that release — Apache 2.0 conversion has fired | §7 + FSL Future License Grant |
| Bank sells "Computer Use as a Service" to multiple third-party banks using Wide-Moat under the hood | Forbidden — canonical Competing Use the licence exists to prevent | FSL Competing Use; §6 reaffirms |

## Risks of getting this wrong

If we ship stock FSL with no clarification, the conservative reading bank Legal
reaches is: "internal use" means the legal entity that signed, not its parent
or subsidiaries. A holding company deploying for itself plus three subsidiaries
arguably needs four licences, which the licence cannot grant separately because
all four entities pull from the same source. Tier-1 counsel will not litigate
this; they will stop onboarding and demand a side letter (Option 4, with all
its per-deal cost). Worst case, counsel concludes the ambiguity is irreducible
and skips Wide-Moat entirely. The Apache LEGAL-721 thread is the open record
of the same pattern playing out for Liquibase.

If we publish a vague FAQ instead of a binding instrument, the gap a bad actor
exploits is the reverse direction: a systems integrator reads the FAQ
permissively, deploys for multiple unrelated client banks, and markets the
result as a turnkey offering. The FAQ has no legal weight to push back.
Option 3's instrument closes that gap because §3 binds the operator's rights
to a single named licensee and §6 reaffirms the multi-tenant prohibition.

## Open questions for the user

Cap 3.

1. Public-sector deployments: when the licensee is a state agency, the §1
   50%-control test does not map cleanly onto inter-agency relationships.
   Add a §8 for sovereign / government structures or leave it to bilateral
   negotiation? ([gh issue placeholder: gov-sector-permissions])
2. Academic consortia (university running the platform for partner universities
   under a grant): treat under §2 (joint venture) or carve out a separate §8
   with explicit non-commercial scope mirroring FSL Permitted Purpose 3?
   ([gh issue placeholder: academic-consortia-permissions])
3. Is the "irrevocable, binds successors and assigns" wording in §0 strong
   enough to survive an acquisition of Wide-Moat? Legal review should confirm
   the formula matches the standard used in irrevocable patent grants.
   ([gh issue placeholder: successor-binding-clause])
