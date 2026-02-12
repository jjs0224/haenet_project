// import styles from "./ReviewProgress.module.css";

// import spoon from "../../public/spoon.png";
// import fork from "../../assets/icons/fork.svg";
// import chopstick from "../../assets/icons/chopstick.svg";

// const ICONS = [
//   { key: "spoon", src: spoon },
//   { key: "fork", src: fork },
//   { key: "chopstick", src: chopstick },
// ];

// export default function ReviewProgress({ count }) {
//   return (
//     <div className={styles.wrapper}>
//       {ICONS.map((icon, idx) => {
//         const active = count > idx;
//         return (
//           <img
//             key={icon.key}
//             src={icon.src}
//             alt={icon.key}
//             className={`${styles.icon} ${active ? styles.active : styles.inactive}`}
//           />
//         );
//       })}

//       <span className={styles.text}>
//         {Math.min(count, 3)} / 3
//       </span>
//     </div>
//   );
// }
