"""Agentic Reasoning Engine - Chain-of-Thought & Planning

Provides step-by-step reasoning before generating final responses.
Uses Claude's extended thinking or explicit reasoning prompts.
"""

import json
from typing import Optional, List, Dict, Any
from enum import Enum
import streamlit as st


class ReasoningMode(Enum):
    """Reasoning levels for the AI."""
    SIMPLE = "simple"  # Direct answer
    CHAIN_OF_THOUGHT = "chain_of_thought"  # Step-by-step reasoning
    DEEP = "deep"  # Extensive analysis before responding


def build_reasoning_prompt(query: str, context: str = "", mode: ReasoningMode = ReasoningMode.CHAIN_OF_THOUGHT) -> str:
    """Build a prompt that encourages step-by-step reasoning.
    
    Args:
        query: User's question
        context: RAG context or indexed sources
        mode: Level of reasoning depth
    
    Returns:
        Formatted reasoning prompt
    """
    
    if mode == ReasoningMode.SIMPLE:
        return f"Answer this question directly: {query}"
    
    elif mode == ReasoningMode.CHAIN_OF_THOUGHT:
        reasoning_prompt = f"""Break down this problem step-by-step:

1. First, identify the key concepts and what's being asked
2. List what you know (from context) and what you need to infer
3. Work through the logic/math/reasoning
4. State your conclusion
5. Verify against the context provided

QUESTION: {query}

{f'CONTEXT:\n{context}' if context else ''}

Now, provide a clear, step-by-step response."""
        return reasoning_prompt
    
    elif mode == ReasoningMode.DEEP:
        reasoning_prompt = f"""You are a thoughtful expert. Before answering, think deeply:

1. **Problem Analysis**: What is the core question? What are the sub-questions?
2. **Information Gathering**: What facts from the context are relevant? What assumptions are needed?
3. **Critical Thinking**: What are potential alternative interpretations?
4. **Reasoning Path**: Walk through your logic step-by-step
5. **Verification**: Cross-check your answer against the source material
6. **Final Answer**: Provide a comprehensive, well-reasoned response

QUESTION: {query}

{f'SOURCES/CONTEXT:\n{context}' if context else ''}

Provide your complete reasoning and final answer."""
        return reasoning_prompt
    
    return query


def extract_reasoning_steps(response: str) -> Dict[str, Any]:
    """Extract reasoning steps from a response.
    
    Args:
        response: LLM response containing reasoning
    
    Returns:
        Dict with 'thinking' and 'answer' keys
    """
    
    # Simple heuristic: look for step markers
    steps = []
    current_step = []
    
    for line in response.split('\n'):
        if any(line.startswith(marker) for marker in ['1.', '2.', '3.', '4.', '5.', '**']):
            if current_step:
                steps.append('\n'.join(current_step))
            current_step = [line]
        else:
            current_step.append(line)
    
    if current_step:
        steps.append('\n'.join(current_step))
    
    return {
        "thinking": steps[:-1] if len(steps) > 1 else [],
        "answer": steps[-1] if steps else response
    }


def render_reasoning_ui(reasoning_dict: Dict[str, Any], expanded: bool = False):
    """Render reasoning steps in the Streamlit UI.
    
    Args:
        reasoning_dict: Output from extract_reasoning_steps
        expanded: Whether to show reasoning expanded by default
    """
    if reasoning_dict.get("thinking"):
        with st.expander("🧠 Show Reasoning Steps", expanded=expanded):
            for i, step in enumerate(reasoning_dict["thinking"], 1):
                st.markdown(f"**Step {i}:**")
                st.markdown(step)
    
    st.markdown("**Answer:**")
    st.markdown(reasoning_dict.get("answer", ""))


class AgenticPlanner:
    """Multi-step planning agent for complex queries."""
    
    def __init__(self, llm_generator):
        """Initialize the planner.
        
        Args:
            llm_generator: Function that takes messages and returns response
        """
        self.llm_generator = llm_generator
    
    def decompose_query(self, query: str, context: str = "") -> List[str]:
        """Break a complex query into sub-tasks.
        
        Args:
            query: Complex question
            context: Available context
        
        Returns:
            List of sub-questions
        """
        decompose_prompt = f"""Break this question into 3-5 simpler sub-questions that, when answered, fully address the main question.
        
MAIN QUESTION: {query}

List each sub-question as:
1. ...
2. ...
etc.

Provide ONLY the numbered list, no extra text."""
        
        response = self.llm_generator([{"role": "user", "content": decompose_prompt}])
        
        # Parse numbered list
        sub_questions = []
        for line in response.split('\n'):
            line = line.strip()
            if line and line[0].isdigit():
                # Remove number and dot/parenthesis
                q = line.lstrip('0123456789.)) ').strip()
                if q:
                    sub_questions.append(q)
        
        return sub_questions
    
    def answer_sub_questions(self, sub_questions: List[str], context: str = "") -> Dict[str, str]:
        """Answer each sub-question.
        
        Args:
            sub_questions: List of sub-questions
            context: Available context
        
        Returns:
            Dict mapping questions to answers
        """
        answers = {}
        for q in sub_questions:
            prompt = f"{q}\n\nContext: {context}" if context else q
            response = self.llm_generator([{"role": "user", "content": prompt}])
            answers[q] = response
        
        return answers
    
    def synthesize_answer(self, original_query: str, sub_answers: Dict[str, str]) -> str:
        """Combine sub-answers into comprehensive final answer.
        
        Args:
            original_query: Original question
            sub_answers: Dict of sub-question answers
        
        Returns:
            Synthesized final answer
        """
        synthesis_prompt = f"""Original question: {original_query}

Here are answers to sub-questions:
"""
        for q, a in sub_answers.items():
            synthesis_prompt += f"\nQ: {q}\nA: {a}\n"
        
        synthesis_prompt += "\nNow provide a comprehensive, cohesive answer to the original question by synthesizing the above information."
        
        response = self.llm_generator([{"role": "user", "content": synthesis_prompt}])
        return response
    
    def plan_and_solve(self, query: str, context: str = "") -> Dict[str, Any]:
        """Complete agentic planning workflow.
        
        Args:
            query: User's question
            context: Available context
        
        Returns:
            Dict with plan, sub-answers, and final answer
        """
        sub_qs = self.decompose_query(query, context)
        sub_answers = self.answer_sub_questions(sub_qs, context)
        final_answer = self.synthesize_answer(query, sub_answers)
        
        return {
            "original_query": query,
            "decomposition": sub_qs,
            "sub_answers": sub_answers,
            "final_answer": final_answer
        }
