/**
 * Company Voice and Style Guide for Task 2: Inbox Agent
 * Defines tone, structural conventions, and grounding principles for customer communications.
 */

export interface VoiceGuideConfig {
  companyName: string;
  supportTeamName: string;
  tone: string[];
  principles: string[];
  greetingTemplate: (customerName?: string) => string;
  signoffTemplate: (consultantName?: string) => string;
}

export const COMPANY_VOICE_GUIDE: VoiceGuideConfig = {
  companyName: 'Brilliant Directories Support & Technical Services',
  supportTeamName: 'AI Technical Consulting Team',
  tone: [
    'Empathetic and customer-centric',
    'Clear, practical, and action-oriented',
    'Professional without being overly formal',
    'Transparent about technical steps and prerequisites',
  ],
  principles: [
    '1. Ground every technical instruction in verified Brilliant Directories Solution Center documentation.',
    '2. Never speculate, guess, or invent settings paths, add-ons, or custom workarounds.',
    '3. Provide exact dashboard navigation paths (e.g., Settings > Domain Manager, or Finance > Membership Plans).',
    '4. Include source links to official documentation articles and mention screenshots where available.',
    '5. If an inquiry requires account-level billing changes or custom widget development, clearly guide the customer on next steps or escalate to an expert.',
    '6. Avoid corporate jargon; keep explanations step-by-step and approachable for non-technical directory owners.',
  ],
  greetingTemplate: (customerName?: string): string => {
    return customerName && customerName.trim()
      ? `Hello ${customerName.trim()},`
      : 'Hello,';
  },
  signoffTemplate: (consultantName?: string): string => {
    const name = consultantName || 'Brilliant Directories Technical Support';
    return `Best regards,\n${name}\nBrilliant Directories Support & Technical Consulting`;
  },
};
