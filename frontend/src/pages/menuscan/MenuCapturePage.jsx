import { useNavigate } from "react-router-dom";
import CaptureFlow from "../../components/camera/CaptureFlow";

export default function MenuCapturePage() {
  const navigate = useNavigate();

  return (
    <CaptureFlow
      onDone={(file) => {
        navigate("/result", {
          state: { file }
        });
      }}
    />
  );
}
