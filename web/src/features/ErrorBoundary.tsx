// Catches a bug thrown while a panel renders, so that one panel's crash does not blank the whole page.
import { Component, type ReactNode } from 'react';

type Props = { name: string; children: ReactNode };

export class ErrorBoundary extends Component<Props, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return <p className="error" role="alert">The {this.props.name} failed: {this.state.error.message}</p>;
    }
    return this.props.children;
  }
}
