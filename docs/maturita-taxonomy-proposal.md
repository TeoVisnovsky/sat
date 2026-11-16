# Slovak Maturita taxonomy proposal

This document records the approved taxonomy implemented by the Maturita importer.

## Reviewed scope

- Years represented: 2008-2019 and 2022-2026.
- One canonical test form per subject and year.
- Slovak language and literature: 17 tests, 1,088 questions, 136 shared passage sections.
  - 680 single-choice questions.
  - 408 short-text questions.
- Mathematics: 17 tests, 510 questions.
  - 340 short numeric-answer questions.
  - 170 single-choice questions with choices A-E.
- The 2011 Slovak PDF has a broken embedded character map and was reviewed from rendered pages.
- The official target-requirement catalogues and the detailed SJL educational standard were reviewed alongside the papers.

For answer keys containing several shuffled test codes, only the column matching the chosen paper will be imported. Alternate orderings will not create duplicate questions.

The 2008 A/B papers are an exception: they are described as levels, not merely shuffled codes. The default proposal is to use level A only so that there is still one paper per subject and year.

## Taxonomy model

Each question should have separate facets instead of one overloaded label:

1. **Source metadata** - subject, year, canonical test code, question number and source page.
2. **Content category** - what knowledge area the question belongs to.
3. **Skill** - what the learner must do.
4. **Format** - single choice, numeric answer or short text.
5. **Estimated difficulty** - an explicitly non-official estimate.
6. **Stimulus/section** - the shared passage or source material, when applicable.

A question may have one primary category and multiple secondary skill tags.

## Proposed Slovak categories

### 1. Reading comprehension and text analysis

- Find explicit information
- Infer implicit information
- Determine main idea, topic or message
- Determine authorial intention or communicative purpose
- Interpret a word, phrase or sentence in context
- Connect information across sentences or paragraphs
- Evaluate whether a statement follows from the text
- Identify relationships, causes, consequences or character motivations

### 2. Language

- Phonetics, phonology and pronunciation
- Orthography and punctuation
- Lexicology and semantics
- Phraseology
- Word formation
- Morphology and grammatical categories
- Syntax and sentence structure
- Text syntax, cohesion and paragraph structure
- Language history, standard language and codification
- Language styles, registers, stylistic procedures and functional genres
- Rhetoric, communication, information sources and editing

### 3. Literature

- Literary kind and genre
- Narrative perspective, speaker and character
- Composition, plot and dramatic structure
- Theme, motif, conflict and characterisation
- Figurative language and stylistic devices
- Verse, stanza, rhyme and metre
- Literary periods and movements
- Authors and works
- Interpretation of a literary passage

## Proposed Slovak skill tags

- Vyhľadanie
- Vybavenie vedomosti
- Identifikácia a klasifikácia
- Odvodenie
- Interpretácia
- Aplikácia a transformácia
- Porovnanie a syntéza

Every Slovak question also has one of three source labels: `Z textu`, `Naučené vedomosti`, or `Text a vedomosti`.

## Slovak passage grouping

Every paper contains eight passage sections. Each section contains eight consecutive questions: five single-choice questions followed by three short-answer questions.

Each passage should become a reusable `stimulus` record with:

- year and section number;
- author, title and source attribution when present;
- full passage content and associated images;
- broad type: literary or non-literary;
- form: prose, poetry, drama, article/news, interview, essay/criticism, popular-science, practical/administrative, advertising/web or multi-text;
- ordered links to its eight questions.

This makes it possible to practise one complete passage, several selected passages or a full test without repeating the passage in every question.

## Proposed Mathematics categories

The hierarchy follows the official target-requirement catalogue, with a few user-friendly subdivisions.

### 1. Foundations of mathematics

- Logic and statements
- Sets and intervals
- Numbers, ratios, percentages and proportionality
- Algebraic expressions and manipulation
- Number theory and divisibility
- Equations, inequalities and systems

### 2. Functions and sequences

- Function concepts, properties and graph interpretation
- Sequences and series
- Linear and quadratic functions
- Polynomial, power and rational functions
- Exponential and logarithmic functions
- Trigonometric functions

### 3. Planimetry

- Triangles
- Quadrilaterals and polygons
- Circles
- Similarity, congruence and transformations
- Coordinate and analytic geometry
- Geometric loci and constructions

### 4. Stereometry

- Spatial visualisation and projections
- Coordinates and lines/planes in space
- Metric relationships in space
- Solids, surface area and volume

### 5. Combinatorics, probability and statistics

- Counting and combinatorics
- Probability
- Statistics and data interpretation

## Approved Mathematics competencies

- Výpočtová zručnosť
- Algebraické uvažovanie
- Matematické modelovanie
- Funkčné a grafické uvažovanie
- Geometrické a priestorové uvažovanie
- Logické uvažovanie
- Práca s údajmi a pravdepodobnosťou

Method-level labels that could reveal a solution (for example, naming a theorem) are not shown before submission.

## Difficulty

The official papers do not label individual questions by difficulty. The proposal is to store two different measures:

- `estimated_difficulty`: introductory, standard or challenging;
- `empirical_difficulty`: calculated later from correctness rate and response time.

The estimate should use a transparent rubric:

- **Introductory** - direct retrieval, direct definition or one routine operation.
- **Standard** - application in context or a short chain of two to three steps.
- **Challenging** - non-obvious inference, several linked concepts or a longer multi-step solution.

This remains separate from the existing personal rating: easy, medium or hard for me.

## Practice modes

### Full test

- Select subject and year.
- Use the one canonical test code.
- Preserve official order and official time limit.
- Allow pause only in an explicitly untimed practice mode.
- Show unanswered questions and a final score summary.

### Passage practice for Slovak

- Practise one of the eight passages.
- Select several passage sections and keep their questions together and ordered.
- Filter passages by literary/non-literary form, genre or year.

### Mathematics sections

- Questions 1-20: numeric-answer section.
- Questions 21-30: A-E choice section.
- Practise either official section, selected categories or a chosen random question count.

### Custom practice

- Filter by subject, year, category, skill, answer format, estimated difficulty, personal difficulty and progress.
- Optionally keep Slovak passage groups intact instead of shuffling individual questions.

## Data-model changes proposed before import

- `exams`: subject, year, canonical code, level/variant, time limit and source.
- `stimuli`: shared passages, figures, tables and other common material.
- `questions`: exam, official ordinal, stimulus, answer format, points and estimated difficulty.
- `choices`: ordered, variable-length choices rather than an A-D constraint.
- `categories` and hierarchical `skills`.
- `question_skills`: many-to-many assignment with primary/secondary status and confidence.
- `answer_rules`: accepted answers, normalisation mode, strict spelling and official evaluator notes.
- `exam_attempts`: timed or untimed full-test sessions.
- `exam_attempt_answers`: answers, status, timing and final scoring inside a session.
- Portable hashed assets so diagrams and passage images survive database transfer and sync.
- Extraction provenance: source PDF, page, key column/test code and review status.

## Approved decisions

- Two separate Maturita banks: Slovak language and literature, and mathematics.
- Use level A for the exceptional 2008 A/B papers.
- Keep passage sections together and in order by default, while allowing category filters, passage-free practice and full shuffling.
- Offer timed unpausable and untimed pausable full-test practice.
- Use introductory, standard and challenging as explicitly estimated difficulty labels.
- Check Slovak short answers against the official rubric and allow the learner to override a strict mismatch.
- Keep the general interface in English, with Slovak category, subcategory, competency and source labels.
- Keep original PDFs out of the public repository; publish the service and derived banks later after a separate distribution decision.
