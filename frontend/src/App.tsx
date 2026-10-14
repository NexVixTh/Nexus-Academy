import { AppProvider, useApp } from "./context/AppContext";
import { AppShell } from "./components/layout/AppShell";
import { CommandCenter } from "./components/home/CommandCenter";
import { TutorStudio } from "./components/tutor/TutorStudio";
import { QuizStudio } from "./components/quiz/QuizStudio";
import { MasteryDashboard } from "./components/mastery/MasteryDashboard";
import { DocumentLibrary } from "./components/documents/DocumentLibrary";

function MainViewRouter() {
  const { activeTab } = useApp();

  switch (activeTab) {
    case "home":
      return <CommandCenter />;
    case "tutor":
      return <TutorStudio />;
    case "quiz":
      return <QuizStudio />;
    case "mastery":
      return <MasteryDashboard />;
    case "library":
      return <DocumentLibrary />;
    default:
      return <CommandCenter />;
  }
}

export default function App() {
  return (
    <AppProvider>
      <AppShell>
        <MainViewRouter />
      </AppShell>
    </AppProvider>
  );
}