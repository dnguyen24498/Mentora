import type {
  ArtifactSummary,
  ReviewPackage,
  ReviewScene,
  ReviewSection,
  ReviewState,
} from '../api/client'

/** Shared review fixtures for the page tests (component tests stay server-free). */

export const INSTITUTION = 'university-001'
export const ARTIFACT = '1e4c06bc-f29e-4ba4-9b39-b0b2cf5f4f1e'

export function makeScene(order: number, overrides: Partial<ReviewScene> = {}): ReviewScene {
  const sceneId = `ppt/slides/slide${order + 1}.xml`
  return {
    order,
    scene_id: sceneId,
    fidelity: 'STRUCTURAL_RENDERED',
    render_status: 'RENDERED',
    fallback_asset: `assets/${order}.svg`,
    render_url: `/artifacts/${ARTIFACT}/review-package/renders/${order}`,
    requires_review: false,
    missing_fonts: [],
    warnings: [],
    notes: `Notes for slide ${order + 1}`,
    text: [`Slide ${order + 1} body`],
    object_count: 1,
    step_count: 1,
    renderer: null,
    source_ref: {},
    ...overrides,
  }
}

export function makeSection(
  order: number,
  sectionId: string,
  sceneId: string,
  script: string | null,
): ReviewSection {
  return {
    order,
    section_id: sectionId,
    type: 'EXPLANATION',
    scene_id: sceneId,
    scene_step_id: `${sceneId}#step-0`,
    safe_markers: [`${sceneId}#step-0`],
    script,
    scene_fidelity: 'STRUCTURAL_RENDERED',
    requires_review: false,
  }
}

export function makePackage(overrides: Partial<ReviewPackage> = {}): ReviewPackage {
  return {
    artifact_id: ARTIFACT,
    package_id: 'pkg-abc',
    prefix: 'packages/pkg-abc',
    course_id: 'course-1',
    course_version: '3',
    content_package_version: 'cpv-abc',
    lesson_plan_version: 'lp-abc',
    knowledge_index_version: 'unindexed',
    teaching_graph_version: null,
    created_at: '2026-10-16T09:00:00Z',
    state: 'READY',
    publishable: true,
    requires_review: false,
    scene_count: 2,
    file_count: 5,
    renderer: {
      name: 'local-structural-svg',
      version: '1.0.0',
      engine: 'stdlib-svg',
      config_hash: 'hash',
      data_region: 'local',
    },
    placeholder_notice:
      'Structural placeholder render — not a native PowerPoint render. Renderer technology is an open decision (DEC-TECH-005 / FND-002).',
    lesson_order: [
      makeSection(0, 'sec-1', 'ppt/slides/slide1.xml', 'Explain slide 1'),
      makeSection(1, 'sec-2', 'ppt/slides/slide2.xml', null),
    ],
    scenes: [makeScene(0), makeScene(1)],
    ...overrides,
  }
}

export function makeState(overrides: Partial<ReviewState> = {}): ReviewState {
  return {
    artifact_id: ARTIFACT,
    version_id: 'version-1',
    version_status: 'DRAFT',
    package_id: 'pkg-abc',
    content_package_version: 'cpv-abc',
    state: 'READY',
    publishable: true,
    requires_review: false,
    stale: false,
    blocking_scene_orders: [],
    decision: null,
    draft: null,
    draft_count: 0,
    ...overrides,
  }
}

export function makeArtifact(overrides: Partial<ArtifactSummary> = {}): ArtifactSummary {
  return {
    artifact_id: ARTIFACT,
    course_id: 'course-1',
    version_id: 'version-1',
    filename: 'revised-deck.pptx',
    media_type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    sha256: 'a'.repeat(64),
    byte_size: 16_700_000,
    object_key: 'objects/aa/…',
    created_at: '2026-10-16T08:30:00Z',
    ...overrides,
  }
}
