"""Streaming Responses - Token-by-Token Output Display

Implements real-time streaming of LLM responses with visible token generation.
Improves perceived performance and allows users to see reasoning as it happens.
"""

from typing import Generator, List, Dict, Any, Optional
import streamlit as st
import time


class StreamingResponseBuilder:
    """Manages streaming LLM responses."""
    
    def __init__(self):
        """Initialize builder."""
        self.buffer = ""
        self.token_count = 0
        self.start_time = None
    
    def start(self):
        """Mark start of streaming."""
        self.start_time = time.time()
        self.buffer = ""
        self.token_count = 0
    
    def add_token(self, token: str):
        """Add a token to the stream.
        
        Args:
            token: Token text
        """
        self.buffer += token
        self.token_count += 1
    
    def get_content(self) -> str:
        """Get accumulated content.
        
        Returns:
            Full buffered content
        """
        return self.buffer
    
    def get_stats(self) -> Dict[str, Any]:
        """Get streaming statistics.
        
        Returns:
            Dict with token count, elapsed time, speed
        """
        elapsed = time.time() - self.start_time if self.start_time else 0
        speed = self.token_count / elapsed if elapsed > 0 else 0
        
        return {
            "token_count": self.token_count,
            "elapsed_seconds": elapsed,
            "tokens_per_second": speed
        }


def stream_llm_response(stream_generator: Generator, show_stats: bool = True) -> str:
    """Stream LLM response token-by-token in Streamlit.
    
    Args:
        stream_generator: Generator yielding response tokens
        show_stats: Whether to show performance stats
    
    Returns:
        Full accumulated response
    """
    builder = StreamingResponseBuilder()
    builder.start()
    
    # Create placeholder for streaming output
    response_placeholder = st.empty()
    stats_placeholder = st.empty() if show_stats else None
    
    # Stream tokens
    with response_placeholder.container():
        response_area = st.empty()
        
        for token in stream_generator:
            builder.add_token(token)
            
            # Update display every few tokens to reduce re-renders
            if builder.token_count % 10 == 0:
                response_area.markdown(builder.get_content())
            
            # Update stats
            if stats_placeholder and builder.token_count % 50 == 0:
                stats = builder.get_stats()
                with stats_placeholder.container():
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Tokens", stats["token_count"])
                    col2.metric("Time", f"{stats['elapsed_seconds']:.1f}s")
                    col3.metric("Speed", f"{stats['tokens_per_second']:.1f} t/s")
        
        # Final update
        response_area.markdown(builder.get_content())
    
    # Final stats
    if show_stats:
        stats = builder.get_stats()
        with stats_placeholder.container():
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Tokens", stats["token_count"])
            col2.metric("Total Time", f"{stats['elapsed_seconds']:.2f}s")
            col3.metric("Average Speed", f"{stats['tokens_per_second']:.2f} t/s")
    
    return builder.get_content()


def stream_with_formatting(stream_generator: Generator, format_type: str = "markdown") -> str:
    """Stream response with real-time formatting.
    
    Args:
        stream_generator: Generator yielding tokens
        format_type: 'markdown', 'code', or 'plain'
    
    Returns:
        Full response
    """
    builder = StreamingResponseBuilder()
    builder.start()
    
    output = st.empty()
    
    for token in stream_generator:
        builder.add_token(token)
        
        if builder.token_count % 15 == 0:
            content = builder.get_content()
            
            if format_type == "markdown":
                output.markdown(content)
            elif format_type == "code":
                output.code(content)
            else:
                output.text(content)
    
    # Final render
    content = builder.get_content()
    if format_type == "markdown":
        output.markdown(content)
    elif format_type == "code":
        output.code(content)
    else:
        output.text(content)
    
    return content


def render_thinking_process(stream_generator: Generator) -> tuple[str, str]:
    """Stream response showing thinking/reasoning separately.
    
    Args:
        stream_generator: Generator yielding response tokens
    
    Returns:
        Tuple of (thinking, answer)
    """
    builder = StreamingResponseBuilder()
    builder.start()
    
    thinking_container = st.container()
    answer_container = st.container()
    
    full_text = ""
    thinking_text = ""
    answer_text = ""
    in_thinking = False
    
    for token in stream_generator:
        builder.add_token(token)
        full_text += token
        
        # Simple heuristic: look for thinking markers
        if "<think>" in full_text or "[THINKING]" in full_text:
            in_thinking = True
        
        if "</think>" in full_text or "[/THINKING]" in full_text:
            in_thinking = False
        
        if in_thinking:
            thinking_text += token
        else:
            answer_text += token
        
        # Update display
        if builder.token_count % 20 == 0:
            with thinking_container:
                if thinking_text:
                    with st.expander("🧠 Thinking Process", expanded=False):
                        st.markdown(thinking_text)
            
            with answer_container:
                st.markdown(answer_text)
    
    return thinking_text, answer_text


class StreamMetrics:
    """Track streaming metrics for performance monitoring."""
    
    def __init__(self):
        """Initialize metrics."""
        self.sessions = []
    
    def log_session(self, token_count: int, elapsed_seconds: float, model: str):
        """Log a streaming session.
        
        Args:
            token_count: Number of tokens streamed
            elapsed_seconds: Time taken
            model: Model name
        """
        self.sessions.append({
            "tokens": token_count,
            "time": elapsed_seconds,
            "speed": token_count / elapsed_seconds if elapsed_seconds > 0 else 0,
            "model": model,
            "timestamp": time.time()
        })
    
    def get_average_speed(self, model: str = None) -> float:
        """Get average streaming speed.
        
        Args:
            model: Optional model to filter by
        
        Returns:
            Average tokens per second
        """
        relevant = self.sessions
        if model:
            relevant = [s for s in relevant if s["model"] == model]
        
        if not relevant:
            return 0.0
        
        return sum(s["speed"] for s in relevant) / len(relevant)
    
    def render_dashboard(self):
        """Render streaming metrics dashboard."""
        if not self.sessions:
            st.info("No streaming sessions recorded yet.")
            return
        
        col1, col2, col3 = st.columns(3)
        
        total_tokens = sum(s["tokens"] for s in self.sessions)
        total_time = sum(s["time"] for s in self.sessions)
        avg_speed = total_tokens / total_time if total_time > 0 else 0
        
        col1.metric("Total Tokens Streamed", total_tokens)
        col2.metric("Total Time", f"{total_time:.1f}s")
        col3.metric("Average Speed", f"{avg_speed:.2f} t/s")
        
        # Per-model metrics
        st.subheader("Per-Model Performance")
        models = set(s["model"] for s in self.sessions)
        
        for model in models:
            model_sessions = [s for s in self.sessions if s["model"] == model]
            avg_speed = self.get_average_speed(model)
            st.metric(f"{model} Avg Speed", f"{avg_speed:.2f} t/s")
