/**
 * Company Model - The central context object for a founder's company.
 * 
 * This model contains all the metadata that defines a company within PANTHEON:
 * - Mission and vision
 * - Strategic priorities
 * - Constraints (operational, regulatory, resource)
 * - Financial assumptions (unit economics, funding, runway)
 * - Approved knowledge base references
 * - Ownership and governance structure
 * 
 * The model is designed to be flexible for single or multiple company setups,
 * with per-company namespace support.
 */

// Base company model template - can be overridden via UI or API
export const defaultCompanyModel = {
  id: "default",
  name: "My Company",
  tagline: "",
  mission: "To build sustainable, meaningful products that improve people's lives",
  vision: "A world where technology serves humanity's highest purposes",
  description: "",
  
  // Strategic priorities - ranked list
  strategicPriorities: [
    { id: "p1", title: "Product-Market Fit", description: "Validate and achieve product-market fit", status: "active", progress: 0 },
    { id: "p2", title: "Team Growth", description: "Build world-class executive team", status: "active", progress: 0 },
    { id: "p3", title: "Revenue Growth", description: "Achieve sustainable revenue growth", status: "active", progress: 0 },
    { id: "p4", title: "Technical Excellence", description: "Maintain high technical standards and scalability", status: "active", progress: 0 }
  ],
  
  // Constraints - operational, regulatory, resource limitations
  constraints: [
    { id: "c1", title: "Budget Constraint", description: "Monthly burn rate limit", severity: "high", currentValue: 0, targetValue: 50000 },
    { id: "c2", title: "Time to Market", description: "Maximum 12 months from concept to launch", severity: "medium", currentValue: 0, targetValue: 12 },
    { id: "c3", title: "Regulatory Compliance", description: "Must comply with industry regulations", severity: "high", currentValue: 0, targetValue: 100 }
  ],
  
  // Financial assumptions
  financialAssumptions: {
    avgContractValue: 0,
    monthlyChurnRate: 0.02,
    salesCycleMonths: 3,
    marketingBudgetPercent: 15,
    fundingRound: "Pre-seed",
    runwayMonths: 12
  },
  
  // Approved knowledge base - key documents and sources
  approvedKnowledge: [
    { id: "k1", title: "Company Constitution", type: "founding_document", lastUpdated: null, source: "internal" },
    { id: "k2", title: "Product Roadmap", type: "strategic_plan", lastUpdated: null, source: "internal" }
  ],
  
  

/**
 * Decision Record Model
 * Every founder decree becomes a structured decision record.
 */

export const defaultDecisionModel = {
  id: "",
  decision_and_rationale: "",
  original_board_recommendation: "",
  founder_decision: "",
  conditions_and_constraints: "",
  owner: "",
  target_date: "",
  success_criteria: "",
  review_date: "",
  actual_outcome: "",
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

/**
 * Get a specific decision by ID
 * @param {String} decisionId - Decision ID
 * @returns {Object} Decision or default model
 */
export function getDecision(decisionId) {
  const decisions = getAllDecisions();
  return decisionId ? decisions.find(d => d.id === decisionId) || defaultDecisionModel : decisions;
}

/**
 * Get all decision records
 * @returns {Array} Array of decision records
 */
export function getAllDecisions() {
  // In a real implementation, this would fetch from localStorage or backend
  // For now, return empty array - decisions are created via API
  return [];
}

/**
 * Create a new decision record
 * @param {Object} decision - Decision record object
 * @returns {Object} Created decision record
 */
export function createDecision(decision) {
  const newDecision = {
    ...defaultDecisionModel,
    id: `d${Date.now()}`,
    ...decision,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
  // In production, this would call the API: createDecisionRecord
  return newDecision;
}

/**
 * Update a decision record
 * @param {String} decisionId - Decision ID
 * @param {Object} updates - Updates to apply
 * @returns {Object} Updated decision record
 */
export function updateDecision(decisionId, updates) {
  const decision = getDecision(decisionId);
  if (decision.id === defaultDecisionModel.id) return defaultDecisionModel;
  const updated = {
    ...decision,
    ...updates,
    updated_at: new Date().toISOString(),
  };
  // In production, this would call the API: updateDecisionRecord
  return updated;
}

/**
 * Format decision for display
 * @param {Object} decision - Decision record
 * @returns {String} Formatted display string
 */
 export function formatDecision(decision) {
  return `Decision: ${decision.decision_and_rationale.substring(0, 80)}${decision.decision_and_rationale.length > 80 ? '...' : ''}`;
}

// Ownership and governance
  ownership: {
    founder: { name: "", email: "", equity: 100 },
    investors: [],
    boardMembers: []
  },
  
  // Metadata
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
  version: "1.0.0"
};

/**
 * Update company model with new data
 * @param {Object} partialModel - Partial company model to merge
 * @returns {Object} Updated company model
 */
export function updateCompanyModel(partialModel) {
  return {
    ...defaultCompanyModel,
    ...partialModel,
    updatedAt: new Date().toISOString(),
    version: (parseFloat(defaultCompanyModel.version) + 0.1).toString().substring(0, 3) || "1.0"
  };
}

/**
 * Get a specific priority by ID
 * @param {String} priorityId - Priority ID
 * @returns {Object} Priority or null
 */
export function getPriority(priorityId) {
  return defaultCompanyModel.strategicPriorities.find(p => p.id === priorityId) || null;
}

/**
 * Get constraint by ID
 * @param {String} constraintId - Constraint ID
 * @returns {Object} Constraint or null
 */
export function getConstraint(constraintId) {
  return defaultCompanyModel.constraints.find(c => c.id === constraintId) || null;
}

/**
 * Add a new priority
 * @param {Object} priority - Priority object {title, description, status, progress}
 * @returns {Object} Added priority with ID
 */
export function addPriority(priority) {
  const newPriority = { ...priority, id: `p${defaultCompanyModel.strategicPriorities.length + 1}` };
  return updateCompanyModel({ strategicPriorities: [...defaultCompanyModel.strategicPriorities, newPriority] });
}

/**
 * Add a new constraint
 * @param {Object} constraint - Constraint object {title, description, severity, currentValue, targetValue}
 * @returns {Object} Added constraint with ID
 */
export function addConstraint(constraint) {
  const newConstraint = { ...constraint, id: `c${defaultCompanyModel.constraints.length + 1}` };
  return updateCompanyModel({ constraints: [...defaultCompanyModel.constraints, newConstraint] });
}

/**
 * Add approved knowledge document
 * @param {Object} doc - Document {title, type, source}
 * @returns {Object} Added document with ID
 */
export function addApprovedKnowledge(doc) {
  const newDoc = { ...doc, id: `k${defaultCompanyModel.approvedKnowledge.length + 1}`, lastUpdated: new Date().toISOString() };
  return updateCompanyModel({ approvedKnowledge: [...defaultCompanyModel.approvedKnowledge, newDoc] });
}

/**
 * Set financial assumptions
 * @param {Object} assumptions - Financial assumptions object
 * @returns {Object} Updated company model
 */
export function setFinancialAssumptions(assumptions) {
  return updateCompanyModel({ financialAssumptions: { ...defaultCompanyModel.financialAssumptions, ...assumptions } });
}

/**
 * Set ownership
 * @param {Object} ownership - Ownership object
 * @returns {Object} Updated company model
 */
export function setOwnership(ownership) {
  return updateCompanyModel({ ownership });
}/** Set company metadata */
